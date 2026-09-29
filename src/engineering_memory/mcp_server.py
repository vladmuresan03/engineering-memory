"""Source-agnostic MCP access to Engineering Memory.

Run with ``python -m engineering_memory.mcp_server``. The database path may be
set with ``ENGINEERING_MEMORY_DB``; otherwise ``Memory`` uses its own default.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Annotated, Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

if TYPE_CHECKING:
    from .service import Memory


_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_ADDITIVE_WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)
_STATE_WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=False,
)


def create_server(memory: Memory | None = None) -> MCPServer:
    """Build a server, optionally using a supplied memory service for testing."""

    server = MCPServer("Engineering Memory")
    active_memory = memory

    def get_memory() -> Memory:
        nonlocal active_memory
        if active_memory is None:
            from .service import Memory

            db_path = os.environ.get("ENGINEERING_MEMORY_DB")
            active_memory = Memory(db_path=db_path) if db_path else Memory()
        return active_memory

    @server.tool(title="Search engineering memory", annotations=_READ_ONLY)
    def search_memory(
        query: str,
        scope: str | None = None,
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
        include_history: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        """Find provenance-bearing excerpts. Superseded or retracted entries require include_history."""
        return {"matches": get_memory().search(query, scope=scope, limit=limit, include_history=include_history)}

    @server.tool(title="Assemble engineering context", annotations=_READ_ONLY)
    def assemble_context(
        query: str,
        scope: str | None = None,
        max_chars: Annotated[int, Field(ge=300, le=50000)] = 6000,
        include_history: bool = False,
    ) -> str:
        """Build a compact context passage from matching memory entries."""
        return get_memory().context(query, scope=scope, max_chars=max_chars, include_history=include_history)

    @server.tool(title="Get memory source", annotations=_READ_ONLY)
    def get_source(source_id: str) -> dict[str, dict[str, Any] | None]:
        """Look up stored source details and provenance for a source ID."""
        return {"source": get_memory().get_source(source_id)}

    @server.tool(title="Record memory entry", annotations=_ADDITIVE_WRITE)
    def record_memory(
        kind: str,
        content: str,
        scope: str | None = None,
        source_uri: str | None = None,
        title: str | None = None,
        rationale: str | None = None,
        author_kind: str = "unknown",
        author: str | None = None,
        occurred_at: str | None = None,
        idempotency_key: str | None = None,
        related_to: str | None = None,
        relation: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Store a direct, unverified entry. Supply idempotency_key for safe retries; a source URI is an unverified reference, not fetched or checked."""
        return {
            "entry": get_memory().record(
                kind,
                content,
                scope=scope,
                source_uri=source_uri,
                title=title,
                rationale=rationale,
                author_kind=author_kind,
                author=author,
                occurred_at=occurred_at,
                idempotency_key=idempotency_key,
                related_to=related_to,
                relation=relation,
                recorded_by="mcp",
            )
        }

    @server.tool(title="Supersede memory entry", annotations=_STATE_WRITE)
    def supersede_memory(
        old_source_id: str,
        kind: str,
        content: str,
        change_reason: str,
        source_uri: str | None = None,
        title: str | None = None,
        rationale: str | None = None,
        author_kind: str = "unknown",
        author: str | None = None,
        occurred_at: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Record a replacement and hide the old entry from default search; retain its history."""
        old = get_memory().get_source(old_source_id)
        if old is None:
            raise ValueError(f"unknown source_id: {old_source_id}")
        return {
            "entry": get_memory().record(
                kind, content, scope=old["scope"], source_uri=source_uri,
                title=title, rationale=rationale, recorded_by="mcp",
                author_kind=author_kind, author=author, occurred_at=occurred_at,
                idempotency_key=idempotency_key, supersedes=old_source_id,
                change_reason=change_reason,
            )
        }

    @server.tool(title="Retract memory entry", annotations=_STATE_WRITE)
    def retract_memory(
        source_id: str, reason: str, author_kind: str = "unknown", author: str | None = None,
    ) -> dict[str, dict[str, str]]:
        """Withdraw a direct entry from default search, retaining a reason and caller-supplied attribution."""
        return {"entry": get_memory().retract(
            source_id, reason, recorded_by="mcp", author_kind=author_kind, author=author,
        )}

    @server.tool(title="Link memory entries", annotations=_ADDITIVE_WRITE)
    def link_memory(from_id: str, to_id: str, relation: str) -> dict[str, dict[str, str]]:
        """Add an explicit explains, contradicts, or resulted_in relation between existing entries."""
        return {"link": get_memory().link(from_id, to_id, relation)}

    return server


mcp = create_server()


def main() -> None:
    """Serve the MCP protocol over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
