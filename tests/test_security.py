"""Security and data-integrity boundaries for local storage and GitHub import."""

from __future__ import annotations

import json
import sqlite3
import stat
from unittest.mock import patch

import pytest

from engineering_memory import github
from engineering_memory.github import GitHubAPIError, iter_repository
from engineering_memory.store import SCHEMA_VERSION, Store


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_new_database_and_directory_are_private_without_changing_existing_directory(tmp_path) -> None:
    public_parent = tmp_path / "existing-public-directory"
    public_parent.mkdir()
    public_parent.chmod(0o755)

    private_db = public_parent / "new-private-directory" / "memory.db"
    with Store(private_db):
        pass
    assert _mode(public_parent) == 0o755
    assert _mode(private_db.parent) == 0o700
    assert _mode(private_db) == 0o600

    existing_directory = public_parent / "preexisting-directory"
    existing_directory.mkdir()
    existing_directory.chmod(0o755)
    existing_db = existing_directory / "memory.db"
    with Store(existing_db):
        pass
    assert _mode(existing_directory) == 0o755
    assert _mode(existing_db) == 0o600


def test_store_versions_new_schema_and_rejects_partial_sources_table(tmp_path) -> None:
    complete_db = tmp_path / "complete.db"
    with Store(complete_db):
        pass
    with sqlite3.connect(complete_db) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        # A complete database from the pre-versioned generic scaffold is safe
        # to adopt without changing its stored records.
        connection.execute("PRAGMA user_version = 0")
    with Store(complete_db):
        pass
    with sqlite3.connect(complete_db) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

    partial_db = tmp_path / "partial.db"
    with sqlite3.connect(partial_db) as connection:
        connection.execute(
            """CREATE TABLE sources (
                source_id TEXT PRIMARY KEY, source_system TEXT, source_type TEXT,
                scope TEXT, uri TEXT, title TEXT, body TEXT,
                occurred_at TEXT, metadata_json TEXT, indexed_at TEXT
            )"""
        )
    with pytest.raises(RuntimeError, match="missing source columns: memory_kind"):
        Store(partial_db)


def test_default_github_opener_blocks_redirect_before_forwarding_token() -> None:
    received = []

    class RedirectingDirector:
        def __init__(self, handler):
            self.handler = handler

        def open(self, request, *, timeout):
            received.append((request.full_url, request.get_header("Authorization"), timeout))
            return self.handler.redirect_request(
                request, None, 302, "Found", {}, "https://other.example/collect"
            )

    with patch.object(github, "build_opener", side_effect=lambda handler: RedirectingDirector(handler)):
        with pytest.raises(GitHubAPIError, match="redirect blocked") as error:
            list(iter_repository("Acme/Widget", token="secret-token"))

    assert len(received) == 1
    assert received[0][0].startswith("https://api.github.com/")
    assert received[0][1] == "Bearer secret-token"
    assert "secret-token" not in str(error.value)


class _Response:
    status = 200
    headers: dict[str, str] = {}

    def __init__(self, records: list[dict]):
        self.payload = json.dumps(records).encode()

    def read(self) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_only_merged_pull_requests_are_classified_as_changes() -> None:
    def pull(number: int, state: str, merged_at: str | None) -> dict:
        return {
            "number": number,
            "html_url": f"https://github.com/Acme/Widget/pull/{number}",
            "title": f"PR {number}",
            "body": "Proposed implementation",
            "created_at": "2026-01-02T12:00:00Z",
            "state": state,
            "merged_at": merged_at,
        }

    def opener(request, *, timeout):
        if "/pulls?" in request.full_url:
            return _Response(
                [
                    pull(1, "open", None),
                    pull(2, "closed", None),
                    pull(3, "closed", "2026-01-03T12:00:00Z"),
                ]
            )
        return _Response([])

    sources = list(iter_repository("Acme/Widget", max_items=3, opener=opener))
    assert [(source.source_id.rsplit(":", 1)[1], source.memory_kind) for source in sources] == [
        ("1", "Event"),
        ("2", "Event"),
        ("3", "Change"),
    ]
