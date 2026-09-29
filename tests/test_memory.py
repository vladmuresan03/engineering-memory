"""End-to-end behavior of the local memory store and retrieval service."""

from dataclasses import replace
import json

from engineering_memory.cli import main
from engineering_memory.models import Source
from engineering_memory.service import Memory


def source(source_id: str, scope: str = "acme/app") -> Source:
    return Source(
        source_id=source_id,
        title="Make API requests retry once",
        body=(
            "## Decision\nRetry idempotent requests once.\n\n"
            "## Rationale\nTransient connection resets are common.\n\n"
            "## Attempt\nTried three retries but tail latency increased.\n\n"
            "## Outcome\nOne retry reduced observed failures."
        ),
        source_system="wiki",
        source_type="document",
        scope=scope,
        uri=f"https://docs.example.test/{scope}/retry-policy",
        occurred_at="2026-09-01T10:00:00Z",
        metadata={"document_id": 7},
        memory_kind="Change",
    )


def test_ingest_retrieval_and_provenance(tmp_path) -> None:
    memory = Memory(tmp_path / "memory.db")
    first = source("wiki:acme/app:retry-policy")
    assert memory.ingest([first]) == {"sources": 1, "concepts": 5}

    decisions = memory.search("idempotent requests")
    assert any(item["kind"] == "Decision" for item in decisions)
    assert all(item["source_id"] == first.source_id for item in decisions)
    assert all(item["uri"] == first.uri for item in decisions)

    context = memory.context("tail latency", max_chars=600)
    assert "Attempt" in context
    assert first.uri in context
    assert len(context) <= 600
    assert memory.get_source(first.source_id)["metadata"] == {"document_id": 7}
    assert memory.search("idempotent", scope="other/project") == []


def test_reingest_replaces_derived_concepts(tmp_path) -> None:
    memory = Memory(tmp_path / "memory.db")
    first = source("wiki:acme/app:retry-policy")
    memory.ingest([first])
    changed = replace(first, body="## Decision\nUse exponential backoff instead.")
    assert memory.ingest([changed]) == {"sources": 1, "concepts": 2}
    assert memory.search("transient connection") == []
    assert memory.search("exponential backoff")
    assert memory.get_source(first.source_id)["body"] == changed.body


def test_unlabeled_text_is_not_called_a_decision(tmp_path) -> None:
    memory = Memory(tmp_path / "memory.db")
    unlabeled = replace(
        source("support:acme/app:ticket:8"),
        source_system="support",
        source_type="ticket",
        memory_kind="Event",
        body="Maybe we should replace retries with a queue.",
    )
    memory.ingest([unlabeled])
    matches = memory.search("queue")
    assert matches and {item["kind"] for item in matches} == {"Event"}


def test_direct_record_has_provenance_without_external_source(tmp_path) -> None:
    memory = Memory(tmp_path / "memory.db")
    result = memory.record(
        "decision",
        "Use SQLite for local memory.",
        scope="agent-platform",
        recorded_by="test",
    )
    assert result["kind"] == "Decision"
    assert result["provenance"] == "directly_recorded"
    matches = memory.search("SQLite", scope="agent-platform")
    assert len(matches) == 1
    assert matches[0]["source_system"] == "manual"
    assert matches[0]["uri"] is None
    assert memory.get_source(result["source_id"])["metadata"]["recorded_by"] == "test"
    assert "not independently verified" in memory.context("SQLite")


def test_cli_add_is_the_primary_write_path(tmp_path, capsys) -> None:
    database = tmp_path / "memory.db"
    assert main(
        [
            "--db", str(database), "add", "Attempt", "Tried a queue; it added latency.",
            "--scope", "agent-platform",
        ]
    ) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["kind"] == "Attempt"
    assert Memory(database).search("latency", scope="agent-platform")
