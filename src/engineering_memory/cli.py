"""Command-line access to source-neutral memory and optional adapters."""

import argparse
import json
import os
from collections.abc import Sequence

from .service import Memory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engineering-memory")
    parser.add_argument("--db", help="SQLite path (overrides ENGINEERING_MEMORY_DB)")
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="Record a memory directly")
    add.add_argument("kind", help="Event, Change, Decision, Rationale, Attempt, or Outcome")
    add.add_argument("text", help="Memory text")
    add.add_argument("--title", help="Optional short title")
    add.add_argument("--scope", help="Project or team scope")
    add.add_argument("--source-uri", help="Optional reference; not fetched or verified")
    add.add_argument("--rationale", help="Explicit reason for a Decision, stored with it")
    add.add_argument("--author-kind", choices=("human", "agent", "connector", "unknown"), default="unknown")
    add.add_argument("--author", help="Caller-supplied attribution; not verified")
    add.add_argument("--occurred-at", help="Time of the event, if known (separate from capture time)")
    add.add_argument("--idempotency-key", help="Stable key for retrying the same write safely")
    add.add_argument("--related-to", help="ID of a related memory in the same scope")
    add.add_argument("--relation", choices=("explains", "contradicts", "resulted_in"))

    supersede = commands.add_parser("supersede", help="Replace an earlier memory while retaining history")
    supersede.add_argument("old_source_id")
    supersede.add_argument("kind")
    supersede.add_argument("text")
    supersede.add_argument("--reason", required=True, help="Why the earlier memory is being replaced")
    supersede.add_argument("--title")
    supersede.add_argument("--rationale")
    supersede.add_argument("--source-uri")
    supersede.add_argument("--author-kind", choices=("human", "agent", "connector", "unknown"), default="unknown")
    supersede.add_argument("--author")
    supersede.add_argument("--occurred-at")
    supersede.add_argument("--idempotency-key")

    retract = commands.add_parser("retract", help="Withdraw a direct memory while retaining history")
    retract.add_argument("source_id")
    retract.add_argument("--reason", required=True)
    retract.add_argument("--author-kind", choices=("human", "agent", "connector", "unknown"), default="unknown")
    retract.add_argument("--author", help="Caller-supplied attribution; not verified")

    link = commands.add_parser("link", help="Add an explicit relation between two records")
    link.add_argument("from_id")
    link.add_argument("to_id")
    link.add_argument("relation", choices=("explains", "contradicts", "resulted_in"))

    ingest = commands.add_parser("ingest", help="Import records through an optional adapter")
    ingest_sources = ingest.add_subparsers(dest="connector", required=True)
    github = ingest_sources.add_parser("github", help="Import GitHub commits, PRs, and issues")
    github.add_argument("repository", help="owner/repo")
    github.add_argument("--max-items", type=int, default=100, help="Max items per artifact type")

    search = commands.add_parser("search", help="Find memory entries")
    search.add_argument("query")
    search.add_argument("--scope", help="Limit to a project or team scope")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--include-history", action="store_true", help="Include superseded and retracted entries")

    context = commands.add_parser("context", help="Build a provenance-aware context packet")
    context.add_argument("query")
    context.add_argument("--scope", help="Limit to a project or team scope")
    context.add_argument("--max-chars", type=int, default=6000)
    context.add_argument("--include-history", action="store_true", help="Include superseded and retracted entries")

    source = commands.add_parser("source", help="Inspect an indexed source")
    source.add_argument("source_id")

    commands.add_parser("mcp", help="Start the MCP server over stdio")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    memory = Memory(args.db)

    try:
        if args.command == "add":
            result = memory.record(
                args.kind,
                args.text,
                title=args.title,
                scope=args.scope,
                source_uri=args.source_uri,
                rationale=args.rationale,
                author_kind=args.author_kind,
                author=args.author,
                occurred_at=args.occurred_at,
                idempotency_key=args.idempotency_key,
                related_to=args.related_to,
                relation=args.relation,
                recorded_by="cli",
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.command == "supersede":
            old = memory.get_source(args.old_source_id)
            if old is None:
                raise ValueError(f"unknown source_id: {args.old_source_id}")
            result = memory.record(
                args.kind, args.text,
                scope=old["scope"], source_uri=args.source_uri,
                title=args.title, rationale=args.rationale,
                recorded_by="cli", author_kind=args.author_kind, author=args.author,
                occurred_at=args.occurred_at, idempotency_key=args.idempotency_key,
                supersedes=args.old_source_id, change_reason=args.reason,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.command == "retract":
            print(json.dumps(memory.retract(
                args.source_id, args.reason, recorded_by="cli",
                author_kind=args.author_kind, author=args.author,
            ), indent=2))
        elif args.command == "link":
            print(json.dumps(memory.link(args.from_id, args.to_id, args.relation), indent=2))
        elif args.command == "ingest":
            from .github import iter_repository

            token = os.environ.get("GITHUB_TOKEN")
            # Finish adapter reads before writing, so a failed fetch cannot
            # leave only part of a requested batch in the database.
            sources = list(iter_repository(args.repository, token=token, max_items=args.max_items))
            result = memory.ingest(sources)
            print(json.dumps(result, indent=2))
        elif args.command == "search":
            print(json.dumps(memory.search(args.query, args.scope, args.limit, args.include_history), indent=2, ensure_ascii=False))
        elif args.command == "context":
            print(memory.context(args.query, args.scope, args.max_chars, args.include_history))
        elif args.command == "source":
            print(json.dumps(memory.get_source(args.source_id), indent=2, ensure_ascii=False))
        elif args.command == "mcp":
            try:
                from .mcp_server import create_server
            except ModuleNotFoundError as error:
                if error.name in {"mcp", "pydantic"}:
                    raise RuntimeError("install the MCP extra: pip install -e '.[mcp]'") from error
                raise

            create_server(memory).run()
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        build_parser().exit(1, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
