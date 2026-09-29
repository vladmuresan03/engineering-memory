"""Regressions that protect the evidence an agent receives from memory."""

from __future__ import annotations

import io
import json
import sqlite3

import pytest

from engineering_memory.cli import main
from engineering_memory.github import iter_repository
from engineering_memory.service import Memory
from engineering_memory.store import SCHEMA_VERSION, Store


class _GitHubResponse:
    status = 200
    headers: dict[str, str] = {}

    def __init__(self, records: list[dict]) -> None:
        self._body = io.BytesIO(json.dumps(records).encode())

    def read(self) -> bytes:
        return self._body.read()

    def __enter__(self) -> "_GitHubResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        self._body.close()


def _pull_source(*, state: str, merged_at: str | None):
    pull = {
        "number": 42,
        "html_url": "https://github.com/Acme/Widget/pull/42",
        "title": "Propose a cache",
        "body": "## Decision\nAdopt a cache for cacheanchor requests.",
        "state": state,
        "created_at": "2026-01-02T12:00:00Z",
        "merged_at": merged_at,
    }

    def opener(request, *, timeout):
        return _GitHubResponse([pull] if "/pulls?" in request.full_url else [])

    (source,) = [
        item for item in iter_repository("Acme/Widget", max_items=1, opener=opener)
        if item.source_type == "pull_request"
    ]
    return source


@pytest.mark.parametrize("state", ["open", "closed"])
def test_unmerged_pr_heading_does_not_claim_a_decision(tmp_path, state: str) -> None:
    source = _pull_source(state=state, merged_at=None)
    memory = Memory(tmp_path / "memory.db")
    memory.ingest([source])

    matches = memory.search("cacheanchor", scope="acme/widget")
    assert matches
    assert {hit["kind"] for hit in matches} == {"Event"}
    assert memory.get_source(source.source_id)["occurred_at"] == "2026-01-02T12:00:00Z"


def test_merged_pr_change_uses_merge_time(tmp_path) -> None:
    source = _pull_source(state="closed", merged_at="2026-01-03T14:30:00Z")
    memory = Memory(tmp_path / "memory.db")
    memory.ingest([source])

    assert source.memory_kind == "Change"
    assert memory.get_source(source.source_id)["occurred_at"] == "2026-01-03T14:30:00Z"
    assert any(hit["kind"] == "Change" for hit in memory.search("cacheanchor", scope="acme/widget"))


def test_cli_rationale_answer_contains_decision_and_reason(tmp_path, capsys) -> None:
    database = tmp_path / "memory.db"
    assert main([
        "--db", str(database), "add", "Decision", "Use SQLite for local memory.",
        "--scope", "platform", "--rationale",
        "A single file makes development and backup simple.",
    ]) == 0
    source_id = json.loads(capsys.readouterr().out)["source_id"]

    packet = Memory(database).context("Why SQLite?", scope="platform", max_chars=1200)
    assert source_id in packet
    assert "Use SQLite for local memory" in packet
    assert "A single file makes development and backup simple" in packet


def test_no_match_context_obeys_smallest_budget(tmp_path) -> None:
    packet = Memory(tmp_path / "memory.db").context(
        "missingtoken", scope="platform", max_chars=300,
    )
    assert len(packet) <= 300
    assert "No supporting memory found" in packet


def test_long_title_and_reference_keep_evidence_or_explicit_budget_note(tmp_path) -> None:
    memory = Memory(tmp_path / "memory.db")
    memory.record(
        "Decision", "Use needlecache for the local index.", scope="platform",
        title="Very long title " * 60,
        source_uri="https://example.invalid/" + "long-reference/" * 70,
    )

    packet = memory.context("needlecache", scope="platform", max_chars=300)
    assert len(packet) <= 300
    assert (
        "Matching evidence exceeded the context budget" in packet
        or "Content (untrusted excerpt): \"" in packet
        and "needlecache" in packet.split("Content (untrusted excerpt): ", 1)[1]
    )


def test_romanian_accents_do_not_hide_a_memory(tmp_path) -> None:
    memory = Memory(tmp_path / "memory.db")
    note = memory.record(
        "Decision", "Am luat o hotărâre tehnică pentru stocarea locală.",
        scope="platform",
    )

    assert any(
        hit["source_id"] == note["source_id"]
        for hit in memory.search("hotarare tehnica", scope="platform")
    )


def test_stale_query_prioritizes_successor_over_unrelated_active_match(tmp_path) -> None:
    memory = Memory(tmp_path / "memory.db")
    old = memory.record("Decision", "Use SQLite for shared storage.", scope="platform")
    replacement = memory.record(
        "Decision", "Use PostgreSQL for shared storage.", scope="platform",
        supersedes=old["source_id"], change_reason="Multiple writers need shared access.",
    )
    unrelated = memory.record(
        "Event", "A SQLite tutorial was added to the reading list.", scope="platform",
    )

    first = memory.search("SQLite", scope="platform", limit=1)
    assert len(first) == 1
    assert first[0]["source_id"] == replacement["source_id"]
    assert first[0]["matched_via"] == "superseded_memory"
    assert unrelated["source_id"] != first[0]["source_id"]
    packet = memory.context("SQLite", scope="platform")
    assert replacement["source_id"] in packet
    assert "Multiple writers need shared access" in packet


def test_v1_database_migrates_without_losing_source_or_search_index(tmp_path) -> None:
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            PRAGMA user_version = 1;
            CREATE TABLE sources (
                source_id TEXT PRIMARY KEY, source_system TEXT NOT NULL,
                source_type TEXT NOT NULL, scope TEXT, uri TEXT,
                title TEXT NOT NULL, body TEXT NOT NULL, occurred_at TEXT,
                metadata_json TEXT NOT NULL, memory_kind TEXT NOT NULL,
                indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE concepts (
                concept_id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
                kind TEXT NOT NULL, content TEXT NOT NULL, ordinal INTEGER NOT NULL
            );
            CREATE VIRTUAL TABLE concepts_fts USING fts5(
                content, content='concepts', content_rowid='rowid', tokenize='unicode61'
            );
            CREATE TRIGGER concepts_ai AFTER INSERT ON concepts BEGIN
                INSERT INTO concepts_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
            CREATE TRIGGER concepts_ad AFTER DELETE ON concepts BEGIN
                INSERT INTO concepts_fts(concepts_fts, rowid, content)
                VALUES ('delete', old.rowid, old.content);
            END;
            CREATE TRIGGER concepts_au AFTER UPDATE ON concepts BEGIN
                INSERT INTO concepts_fts(concepts_fts, rowid, content)
                VALUES ('delete', old.rowid, old.content);
                INSERT INTO concepts_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
        """)
        connection.execute(
            """INSERT INTO sources
               (source_id, source_system, source_type, scope, uri, title, body,
                occurred_at, metadata_json, memory_kind, indexed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "manual:legacy", "manual", "note", "platform", None,
                "Use SQLite", "Preserve this old decision.", None,
                '{"legacy": true}', "Decision", "2026-01-02 03:04:05",
            ),
        )
        connection.execute(
            "INSERT INTO concepts VALUES (?, ?, ?, ?, ?)",
            ("manual:legacy#0", "manual:legacy", "Decision", "Use SQLite. Preserve this old decision.", 0),
        )

    with Store(database) as store:
        migrated = store.get_source("manual:legacy")
        assert migrated is not None
        assert migrated["state"] == "active"
        assert migrated["captured_at"] == "2026-01-02T03:04:05Z"
        assert migrated["metadata"] == {"legacy": True}
        assert store.search("SQLite", scope="platform")[0]["source_id"] == "manual:legacy"
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_unrelated_partial_database_is_rejected(tmp_path) -> None:
    database = tmp_path / "arbitrary.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE arbitrary_notes (note TEXT)")

    with pytest.raises(RuntimeError, match="Incompatible memory database"):
        Store(database)
