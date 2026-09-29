"""Public memory lifecycle behavior: evidence, correction, and safe retrieval."""

import re

import pytest

from engineering_memory.service import Memory


def test_capture_time_is_distinct_from_event_time(tmp_path) -> None:
    memory = Memory(tmp_path / "memory.db")

    retrospective = memory.record(
        "Decision", "Use SQLite for local development.", scope="platform",
        recorded_by="cli", author_kind="human", author="Ada",
    )
    stored = memory.get_source(retrospective["source_id"])
    assert stored is not None
    assert stored["occurred_at"] is None
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", stored["captured_at"])
    assert retrospective["captured_at"] == stored["captured_at"]
    assert stored["author_kind"] == "human"
    assert stored["author"] == "Ada"

    dated = memory.record(
        "Event", "Migrated the local index.", scope="platform",
        occurred_at="2025-04-01T09:00:00Z",
    )
    assert memory.get_source(dated["source_id"])["occurred_at"] == "2025-04-01T09:00:00Z"
    packet = memory.context("SQLite", scope="platform")
    assert "Event time: unknown" in packet
    assert "attribution: human \"Ada\"" in packet


def test_explicit_rationale_link_assembles_explanation(tmp_path) -> None:
    memory = Memory(tmp_path / "memory.db")
    decision = memory.record(
        "Decision", "Use SQLite for the first local release.", scope="platform",
    )
    rationale = memory.record(
        "Rationale", "A single local file keeps setup and backups simple.",
        scope="platform", related_to=decision["source_id"], relation="explains",
    )

    assert memory.get_source(decision["source_id"])["links"] == [
        {
            "from_id": rationale["source_id"],
            "to_id": decision["source_id"],
            "relation": "explains",
            "created_at": memory.get_source(decision["source_id"])["links"][0]["created_at"],
        }
    ]
    packet = memory.context("Why SQLite?", scope="platform", max_chars=1500)
    assert decision["source_id"] in packet
    assert rationale["source_id"] in packet
    assert "A single local file keeps setup and backups simple" in packet
    assert "not independently verified" in packet


def test_idempotent_retry_preserves_one_record_and_rejects_changed_payload(tmp_path) -> None:
    memory = Memory(tmp_path / "memory.db")
    kwargs = {
        "scope": "platform",
        "recorded_by": "mcp",
        "author_kind": "agent",
        "author": "example-agent",
        "idempotency_key": "write-17",
    }
    first = memory.record("Attempt", "Tried one retry on timeout.", **kwargs)
    replay = memory.record("Attempt", "Tried one retry on timeout.", **kwargs)

    assert first["source_id"] == replay["source_id"]
    assert first["captured_at"] == replay["captured_at"]
    assert first["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True
    assert len(memory.search("timeout", scope="platform")) == 1

    with pytest.raises(ValueError, match="different content"):
        memory.record("Attempt", "Tried three retries on timeout.", **kwargs)
    assert memory.get_source(first["source_id"])["title"] == "Tried one retry on timeout."


def test_supersession_preserves_history_but_hides_stale_claim_by_default(tmp_path) -> None:
    memory = Memory(tmp_path / "memory.db")
    first = memory.record("Decision", "Choose SQLite for the shared service.", scope="platform")
    second = memory.record(
        "Decision", "Choose PostgreSQL for the shared service.", scope="platform",
        supersedes=first["source_id"], change_reason="Team access needs concurrent writers.",
    )

    assert memory.get_source(first["source_id"])["state"] == "superseded"
    assert memory.get_source(second["source_id"])["state"] == "active"
    routed = memory.search("SQLite", scope="platform")
    assert {item["source_id"] for item in routed} == {second["source_id"]}
    assert routed[0]["matched_via"] == "superseded_memory"
    assert routed[0]["historical_source_id"] == first["source_id"]
    assert {item["source_id"] for item in memory.search("SQLite", scope="platform", include_history=True)} == {first["source_id"]}
    assert {item["source_id"] for item in memory.search("PostgreSQL", scope="platform")} == {second["source_id"]}
    assert memory.get_source(second["source_id"])["metadata"]["change_reason"] == "Team access needs concurrent writers."
    assert any(
        edge["relation"] == "supersedes" and edge["to_id"] == first["source_id"]
        for edge in memory.get_source(second["source_id"])["links"]
    )
    assert first["source_id"] not in memory.context("PostgreSQL", scope="platform")
    assert first["source_id"] in memory.context("PostgreSQL", scope="platform", include_history=True)


def test_retraction_retains_auditable_reason_and_hides_claim(tmp_path) -> None:
    memory = Memory(tmp_path / "memory.db")
    note = memory.record("Outcome", "The queue cut latency in half.", scope="platform")

    assert memory.retract(note["source_id"], "Measurement was from a stale dashboard", recorded_by="Ada") == {
        "source_id": note["source_id"], "state": "retracted",
    }
    stored = memory.get_source(note["source_id"])
    assert stored["state"] == "retracted"
    assert stored["metadata"]["retraction"]["reason"] == "Measurement was from a stale dashboard"
    assert stored["metadata"]["retraction"]["recorded_by"] == "Ada"
    assert memory.search("latency", scope="platform") == []
    assert memory.context("latency", scope="platform").endswith(
        "No supporting memory found. Do not infer an answer from this database."
    )
    assert memory.search("latency", scope="platform", include_history=True)[0]["state"] == "retracted"


def test_links_and_supersession_cannot_cross_scopes(tmp_path) -> None:
    memory = Memory(tmp_path / "memory.db")
    first = memory.record("Decision", "Use SQLite for project A.", scope="project-a")
    other = memory.record("Rationale", "One file is enough for project B.", scope="project-b")

    with pytest.raises(ValueError, match="same scope"):
        memory.link(other["source_id"], first["source_id"], "explains")
    with pytest.raises(ValueError, match="same scope"):
        memory.record(
            "Rationale", "An unrelated project rationale.", scope="project-b",
            related_to=first["source_id"], relation="explains",
        )
    with pytest.raises(ValueError, match="same scope"):
        memory.record(
            "Decision", "Use a different database.", scope="project-b",
            supersedes=first["source_id"], change_reason="Different workload",
        )
    assert memory.get_source(first["source_id"])["state"] == "active"
    assert memory.get_source(first["source_id"])["links"] == []


def test_search_returns_bounded_excerpts_and_no_support_when_absent(tmp_path) -> None:
    memory = Memory(tmp_path / "memory.db")
    note = memory.record(
        "Event", "Large investigation. " + ("ordinary detail " * 3000) + "rareanchor near the end.",
        scope="platform",
    )
    matches = memory.search("rareanchor", scope="platform")
    assert len(matches) == 1
    assert matches[0]["source_id"] == note["source_id"]
    assert "rareanchor" in matches[0]["content"]
    assert len(matches[0]["content"]) <= 600
    assert matches[0]["content_length"] > 30_000
    assert memory.search("missingtoken", scope="platform") == []
    assert "No supporting memory found" in memory.context("missingtoken", scope="platform")
