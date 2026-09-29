"""MCP contract tests using the SDK's in-memory client."""

from __future__ import annotations

import pytest

pytest.importorskip("mcp")

from mcp import Client
from mcp.types import TextContent

from engineering_memory.mcp_server import create_server
from engineering_memory.service import Memory


class MemoryStub:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def search(self, query: str, scope: str | None = None, limit: int = 10,
               include_history: bool = False) -> list[dict]:
        self.calls.append(("search", query, scope, limit, include_history))
        return [{"id": "decision:1", "scope": "billing", "content": "Keep invoices immutable"}]

    def context(self, query: str, scope: str | None = None, max_chars: int = 6000,
                include_history: bool = False) -> str:
        self.calls.append(("context", query, scope, max_chars, include_history))
        return "Decision: Keep invoices immutable"

    def get_source(self, source_id: str) -> dict | None:
        self.calls.append(("source", source_id))
        if source_id == "source:1":
            return {"id": source_id, "uri": "https://example.com/adr/1", "scope": "billing"}
        return None

    def record(
        self,
        kind: str,
        content: str,
        *,
        scope: str | None = None,
        source_uri: str | None = None,
        title: str | None = None,
        rationale: str | None = None,
        recorded_by: str = "mcp",
        author_kind: str = "unknown",
        author: str | None = None,
        occurred_at: str | None = None,
        idempotency_key: str | None = None,
        related_to: str | None = None,
        relation: str | None = None,
        supersedes: str | None = None,
        change_reason: str | None = None,
    ) -> dict:
        self.calls.append(("record", kind, content, scope, source_uri, title, recorded_by,
                           rationale, author_kind, author, occurred_at, idempotency_key,
                           related_to, relation, supersedes, change_reason))
        return {
            "id": "decision:2",
            "kind": kind,
            "content": content,
            "scope": scope,
            "source_uri": source_uri,
            "title": title,
            "recorded_by": recorded_by,
        }

    def link(self, from_id: str, to_id: str, relation: str) -> dict:
        self.calls.append(("link", from_id, to_id, relation))
        return {"from_id": from_id, "to_id": to_id, "relation": relation}

    def retract(self, source_id: str, reason: str, *, recorded_by: str = "mcp") -> dict:
        self.calls.append(("retract", source_id, reason, recorded_by))
        return {"source_id": source_id, "state": "retracted"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_source_agnostic_tools_and_results() -> None:
    memory = MemoryStub()
    async with Client(create_server(memory), raise_exceptions=True) as client:
        listing = await client.list_tools()
        tools = {tool.name: tool for tool in listing.tools}
        assert set(tools) == {"search_memory", "assemble_context", "get_source", "record_memory",
                              "supersede_memory", "retract_memory", "link_memory"}
        assert all(
            tools[name].annotations and tools[name].annotations.read_only_hint
            for name in ("search_memory", "assemble_context", "get_source")
        )
        write = tools["record_memory"]
        assert write.annotations and write.annotations.read_only_hint is False
        assert write.annotations.destructive_hint is False
        assert write.annotations.idempotent_hint is False
        assert "unverified reference" in write.description
        assert "not fetched" in write.description
        assert tools["supersede_memory"].annotations.destructive_hint is True
        assert tools["retract_memory"].annotations.destructive_hint is True

        search = await client.call_tool(
            "search_memory", {"query": "invoice", "scope": "billing", "limit": 5}
        )
        assert not search.is_error
        assert search.structured_content == {
            "matches": [{"id": "decision:1", "scope": "billing", "content": "Keep invoices immutable"}]
        }

        context = await client.call_tool("assemble_context", {"query": "invoice", "scope": "billing"})
        assert not context.is_error
        assert any(
            isinstance(block, TextContent) and "Keep invoices immutable" in block.text
            for block in context.content
        )

        source = await client.call_tool("get_source", {"source_id": "source:1"})
        assert not source.is_error
        assert source.structured_content == {
            "source": {"id": "source:1", "uri": "https://example.com/adr/1", "scope": "billing"}
        }

        missing = await client.call_tool("get_source", {"source_id": "missing"})
        assert not missing.is_error
        assert missing.structured_content == {"source": None}

        recorded = await client.call_tool(
            "record_memory",
            {
                "kind": "decision",
                "content": "Keep invoices immutable",
                "scope": "billing",
                "source_uri": "https://example.com/adr/1",
                "title": "Invoice history",
            },
        )
        assert not recorded.is_error
        assert recorded.structured_content == {
            "entry": {
                "id": "decision:2",
                "kind": "decision",
                "content": "Keep invoices immutable",
                "scope": "billing",
                "source_uri": "https://example.com/adr/1",
                "title": "Invoice history",
                "recorded_by": "mcp",
            }
        }

    assert memory.calls == [
        ("search", "invoice", "billing", 5, False),
        ("context", "invoice", "billing", 6000, False),
        ("source", "source:1"),
        ("source", "missing"),
        (
            "record",
            "decision",
            "Keep invoices immutable",
            "billing",
            "https://example.com/adr/1",
            "Invoice history",
            "mcp",
            None,
            "unknown",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ),
    ]


@pytest.mark.anyio
async def test_search_limit_is_validated_before_querying() -> None:
    memory = MemoryStub()
    async with Client(create_server(memory), raise_exceptions=True) as client:
        result = await client.call_tool("search_memory", {"query": "API", "limit": 0})
    assert result.is_error
    assert memory.calls == []


@pytest.mark.anyio
async def test_direct_record_round_trip_through_real_memory(tmp_path) -> None:
    async with Client(create_server(Memory(tmp_path / "memory.db")), raise_exceptions=True) as client:
        recorded = await client.call_tool(
            "record_memory",
            {"kind": "Decision", "content": "Keep invoices immutable", "scope": "billing"},
        )
        assert not recorded.is_error
        source_id = recorded.structured_content["entry"]["source_id"]

        found = await client.call_tool(
            "search_memory", {"query": "invoices", "scope": "billing"}
        )
        assert not found.is_error
        assert found.structured_content["matches"][0]["source_id"] == source_id

        context = await client.call_tool(
            "assemble_context", {"query": "invoices", "scope": "billing"}
        )
        assert not context.is_error
        assert any(
            isinstance(block, TextContent) and "not independently verified" in block.text
            for block in context.content
        )


@pytest.mark.anyio
async def test_mcp_correction_keeps_history_and_supports_safe_retry(tmp_path) -> None:
    async with Client(create_server(Memory(tmp_path / "memory.db")), raise_exceptions=True) as client:
        arguments = {
            "kind": "Decision",
            "content": "Use SQLite for the local index",
            "rationale": "One file keeps installation simple",
            "scope": "project-a",
            "idempotency_key": "storage-choice-1",
        }
        first = await client.call_tool("record_memory", arguments)
        replay = await client.call_tool("record_memory", arguments)
        old_id = first.structured_content["entry"]["source_id"]
        assert replay.structured_content["entry"]["source_id"] == old_id
        assert replay.structured_content["entry"]["idempotent_replay"] is True

        changed = await client.call_tool(
            "supersede_memory",
            {
                "old_source_id": old_id,
                "kind": "Decision",
                "content": "Use PostgreSQL instead of SQLite for the shared index",
                "change_reason": "Multiple writers now need a shared database",
                "idempotency_key": "storage-choice-2",
            },
        )
        assert not changed.is_error
        new_id = changed.structured_content["entry"]["source_id"]
        current = await client.call_tool(
            "search_memory", {"query": "SQLite index", "scope": "project-a"}
        )
        assert {item["source_id"] for item in current.structured_content["matches"]} == {new_id}
        history = await client.call_tool(
            "search_memory", {"query": "SQLite index", "scope": "project-a", "include_history": True}
        )
        assert {item["source_id"] for item in history.structured_content["matches"]} == {old_id, new_id}
        old = await client.call_tool("get_source", {"source_id": old_id})
        assert old.structured_content["source"]["state"] == "superseded"

        retracted = await client.call_tool(
            "retract_memory", {"source_id": new_id, "reason": "Decision withdrawn"}
        )
        assert retracted.structured_content["entry"]["state"] == "retracted"
        now_empty = await client.call_tool(
            "search_memory", {"query": "SQLite index", "scope": "project-a"}
        )
        assert now_empty.structured_content["matches"] == []
