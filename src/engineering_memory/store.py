"""SQLite storage, provenance, and lexical retrieval."""

import json
import os
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

from .extract import extract_concepts
from .models import AUTHOR_KINDS, Source, normalize_timestamp


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    source_system TEXT NOT NULL,
    source_type TEXT NOT NULL,
    scope TEXT,
    uri TEXT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    occurred_at TEXT,
    metadata_json TEXT NOT NULL,
    memory_kind TEXT NOT NULL,
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','superseded','retracted')),
    author_kind TEXT NOT NULL DEFAULT 'unknown' CHECK (author_kind IN ('human','agent','connector','unknown')),
    author TEXT
);
CREATE TABLE IF NOT EXISTS concepts (
    concept_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('Event','Change','Decision','Rationale','Attempt','Outcome')),
    content TEXT NOT NULL,
    ordinal INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS concepts_source_idx ON concepts(source_id);
CREATE INDEX IF NOT EXISTS sources_scope_idx ON sources(scope);
CREATE TABLE IF NOT EXISTS source_links (
    from_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    to_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    relation TEXT NOT NULL CHECK (relation IN ('explains','supersedes','contradicts','resulted_in')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (from_id, to_id, relation),
    CHECK (from_id <> to_id)
);
CREATE INDEX IF NOT EXISTS source_links_to_idx ON source_links(to_id);
CREATE UNIQUE INDEX IF NOT EXISTS one_successor_per_source_idx
    ON source_links(to_id) WHERE relation = 'supersedes';
CREATE VIRTUAL TABLE IF NOT EXISTS concepts_fts USING fts5(
    content, content='concepts', content_rowid='rowid', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS concepts_ai AFTER INSERT ON concepts BEGIN
  INSERT INTO concepts_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER IF NOT EXISTS concepts_ad AFTER DELETE ON concepts BEGIN
  INSERT INTO concepts_fts(concepts_fts, rowid, content)
  VALUES ('delete', old.rowid, old.content);
END;
CREATE TRIGGER IF NOT EXISTS concepts_au AFTER UPDATE ON concepts BEGIN
  INSERT INTO concepts_fts(concepts_fts, rowid, content)
  VALUES ('delete', old.rowid, old.content);
  INSERT INTO concepts_fts(rowid, content) VALUES (new.rowid, new.content);
END;
"""

SCHEMA_VERSION = 2
SOURCE_COLUMNS_V1 = {
    "source_id", "source_system", "source_type", "scope", "uri", "title",
    "body", "occurred_at", "metadata_json", "memory_kind", "indexed_at",
}
SOURCE_COLUMNS = SOURCE_COLUMNS_V1 | {"captured_at", "state", "author_kind", "author"}
CONCEPT_COLUMNS = {"concept_id", "source_id", "kind", "content", "ordinal"}
REQUIRED_SCHEMA_OBJECTS = {
    "sources", "concepts", "concepts_fts", "concepts_ai", "concepts_ad", "concepts_au",
}


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        # A new database may hold private notes or imported repository data.
        # mkdir does not change permissions on a directory that already exists.
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        try:
            existing_version = self._check_existing_schema()
            if existing_version == 1:
                self._migrate_v1()
            self.connection.executescript(SCHEMA)
            self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except Exception:
            self.connection.close()
            raise

    def _check_existing_schema(self) -> int:
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {version} is newer than supported version {SCHEMA_VERSION}"
            )
        objects = {
            row["name"]: row
            for row in self.connection.execute(
                "SELECT name, type, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        }
        if not objects:
            if version:
                raise RuntimeError("Database has a schema version but no memory tables")
            return 0

        source_columns = {
            row["name"] for row in self.connection.execute("PRAGMA table_info(sources)")
        }
        if source_columns and "source_system" not in source_columns:
            raise RuntimeError(
                "This database uses the earlier GitHub-specific schema; "
                "set ENGINEERING_MEMORY_DB to a new file before using the generic schema"
            )
        missing_sources = SOURCE_COLUMNS_V1 - source_columns
        if missing_sources:
            raise RuntimeError(
                "Incompatible memory database: missing source columns: "
                + ", ".join(sorted(missing_sources))
            )
        missing_concepts = CONCEPT_COLUMNS - {
            row["name"] for row in self.connection.execute("PRAGMA table_info(concepts)")
        }
        if missing_concepts:
            raise RuntimeError(
                "Incompatible memory database: missing concept columns: "
                + ", ".join(sorted(missing_concepts))
            )
        missing_objects = REQUIRED_SCHEMA_OBJECTS - objects.keys()
        fts_sql = objects["concepts_fts"]["sql"] if "concepts_fts" in objects else ""
        if missing_objects or "using fts5" not in (fts_sql or "").lower():
            raise RuntimeError(
                "Incompatible memory database: missing or invalid search index and triggers"
            )
        if SOURCE_COLUMNS <= source_columns:
            if "source_links" not in objects:
                raise RuntimeError("Incompatible memory database: missing source links table")
            return 2
        if source_columns == SOURCE_COLUMNS_V1 and version in (0, 1):
            return 1
        raise RuntimeError("Incompatible memory database: incomplete source lifecycle schema")

    def _migrate_v1(self) -> None:
        """Add lifecycle columns without discarding existing local notes."""
        self.connection.executescript("""
            BEGIN IMMEDIATE;
            ALTER TABLE sources ADD COLUMN captured_at TEXT;
            UPDATE sources SET captured_at = indexed_at;
            ALTER TABLE sources ADD COLUMN state TEXT NOT NULL DEFAULT 'active';
            ALTER TABLE sources ADD COLUMN author_kind TEXT NOT NULL DEFAULT 'unknown';
            ALTER TABLE sources ADD COLUMN author TEXT;
            CREATE TABLE source_links (
                from_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
                to_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
                relation TEXT NOT NULL CHECK (relation IN ('explains','supersedes','contradicts','resulted_in')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (from_id, to_id, relation),
                CHECK (from_id <> to_id)
            );
            PRAGMA user_version = 2;
            COMMIT;
        """)

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            self.connection.close()

    def upsert_source(self, source: Source) -> int:
        if source.author_kind not in AUTHOR_KINDS:
            raise ValueError(f"author_kind must be one of: {', '.join(AUTHOR_KINDS)}")
        concepts = extract_concepts(source)
        occurred_at = normalize_timestamp(source.occurred_at)
        self.connection.execute(
            """INSERT INTO sources
               (source_id, source_system, source_type, scope, uri, title, body,
                occurred_at, metadata_json, memory_kind, author_kind, author)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(source_id) DO UPDATE SET
                 source_system=excluded.source_system, source_type=excluded.source_type,
                 scope=excluded.scope, uri=excluded.uri, title=excluded.title,
                 body=excluded.body, occurred_at=excluded.occurred_at,
                 metadata_json=excluded.metadata_json, memory_kind=excluded.memory_kind,
                 author_kind=excluded.author_kind, author=excluded.author,
                 indexed_at=CURRENT_TIMESTAMP""",
            (
                source.source_id,
                source.source_system,
                source.source_type,
                source.scope,
                source.uri,
                source.title,
                source.body,
                occurred_at,
                json.dumps(source.metadata, ensure_ascii=False),
                source.memory_kind,
                source.author_kind,
                source.author,
            ),
        )
        self.connection.execute("DELETE FROM concepts WHERE source_id = ?", (source.source_id,))
        self.connection.executemany(
            "INSERT INTO concepts (concept_id, source_id, kind, content, ordinal) VALUES (?, ?, ?, ?, ?)",
            [
                (f"{source.source_id}#{item.ordinal}", source.source_id, item.kind, item.content, item.ordinal)
                for item in concepts
            ],
        )
        return len(concepts)

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM sources WHERE source_id = ?", (source_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["metadata"] = json.loads(result.pop("metadata_json"))
        result["captured_at"] = _sqlite_timestamp(result["captured_at"])
        return result

    def set_state(self, source_id: str, state: str) -> None:
        if state not in {"active", "superseded", "retracted"}:
            raise ValueError("invalid memory state")
        cursor = self.connection.execute(
            "UPDATE sources SET state = ? WHERE source_id = ?", (state, source_id)
        )
        if cursor.rowcount != 1:
            raise ValueError(f"unknown source_id: {source_id}")

    def update_metadata(self, source_id: str, metadata: dict[str, Any]) -> None:
        cursor = self.connection.execute(
            "UPDATE sources SET metadata_json = ? WHERE source_id = ?",
            (json.dumps(metadata, ensure_ascii=False), source_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"unknown source_id: {source_id}")

    def add_link(self, from_id: str, to_id: str, relation: str) -> None:
        if relation not in {"explains", "supersedes", "contradicts", "resulted_in"}:
            raise ValueError("invalid memory relation")
        if from_id == to_id:
            raise ValueError("a memory cannot link to itself")
        statement = (
            "INSERT INTO source_links (from_id, to_id, relation) VALUES (?, ?, ?)"
            if relation == "supersedes" else
            "INSERT OR IGNORE INTO source_links (from_id, to_id, relation) VALUES (?, ?, ?)"
        )
        try:
            self.connection.execute(statement, (from_id, to_id, relation))
        except sqlite3.IntegrityError as error:
            raise ValueError("this memory already has a successor") from error

    def get_links(self, source_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """SELECT from_id, to_id, relation, created_at FROM source_links
               WHERE from_id = ? OR to_id = ? ORDER BY created_at DESC, from_id, to_id""",
            (source_id, source_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_concepts(self, source_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """SELECT concept_id, kind, ordinal, substr(content, 1, 700) AS content
               FROM concepts WHERE source_id = ? ORDER BY ordinal""",
            (source_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_active_successor(self, source_id: str) -> dict[str, Any] | None:
        """Follow explicit supersession to the current record, if one exists."""
        seen = {source_id}
        current_id = source_id
        for _ in range(20):
            row = self.connection.execute(
                """SELECT from_id FROM source_links
                   WHERE to_id = ? AND relation = 'supersedes'""",
                (current_id,),
            ).fetchone()
            if row is None or row["from_id"] in seen:
                return None
            current_id = row["from_id"]
            seen.add(current_id)
            current = self.get_source(current_id)
            if current is None or current["state"] == "retracted":
                return None
            if current["state"] == "active":
                return current
        return None

    def search(
        self, query: str, scope: str | None = None, limit: int = 10,
        include_history: bool = False,
    ) -> list[dict[str, Any]]:
        stop_words = {"a", "an", "and", "are", "after", "current", "de", "did", "do", "does", "for", "how", "in", "is", "now", "of", "on", "or", "should", "stop", "stopped", "the", "to", "using", "was", "we", "what", "when", "where", "which", "who", "why"}
        tokens = [token for token in re.findall(r"\w+", query, flags=re.UNICODE) if token.lower() not in stop_words]
        if not tokens:
            return []
        expression = " OR ".join(f'"{token}"' for token in tokens[:12])
        limit = max(1, min(limit, 50))
        rows = self.connection.execute(
            """SELECT concepts.concept_id, concepts.kind,
                      substr(snippet(concepts_fts, 0, '', '', ' … ', 48), 1, 600) AS content,
                      concepts.content AS raw_content,
                      length(concepts.content) AS content_length, concepts.ordinal,
                      sources.source_id, sources.source_system, sources.source_type,
                      sources.scope, sources.uri, sources.title, sources.occurred_at,
                      sources.captured_at, sources.state, sources.author_kind, sources.author,
                      json_extract(sources.metadata_json, '$.recorded_by') AS capture_channel,
                      bm25(concepts_fts) AS score
               FROM concepts_fts
               JOIN concepts ON concepts.rowid = concepts_fts.rowid
               JOIN sources ON sources.source_id = concepts.source_id
               WHERE concepts_fts MATCH ?
                 AND (? IS NULL OR sources.scope = ?)
                 AND (? OR sources.state = 'active')
               ORDER BY score, sources.occurred_at DESC
               LIMIT ?""",
            (expression, scope, scope, int(include_history), min(limit * 5, 200)),
        ).fetchall()
        results = []
        unique_tokens = {_fold(token) for token in tokens[:12]}
        minimum_coverage = 0.5 if len(unique_tokens) <= 2 else 0.5 + 1e-9
        for row in rows:
            item = dict(row)
            raw = _fold(item.pop("raw_content"))
            coverage = sum(token in raw for token in unique_tokens) / len(unique_tokens)
            # A single shared topic word is not evidence for a detailed
            # question. This is a conservative lexical gate, not an answer
            # verifier; the evaluation suite tracks its recall tradeoff.
            if coverage < minimum_coverage:
                continue
            item["query_coverage"] = round(coverage, 3)
            results.append(item)
            if len(results) >= limit:
                break
        for item in results:
            item["captured_at"] = _sqlite_timestamp(item["captured_at"])
        return results


def _sqlite_timestamp(value: str) -> str:
    """Expose SQLite's UTC CURRENT_TIMESTAMP as an explicit UTC timestamp."""
    return value.replace(" ", "T") + "Z" if " " in value and not value.endswith("Z") else value


def _fold(value: str) -> str:
    """Match unicode61's default accent-insensitive search in our coverage gate."""
    return "".join(
        character for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )
