# Engineering Memory

**Persistent engineering memory for people and AI coding agents.**

Engineering Memory is an early, open-source local database for recording what happened, what changed, what was decided, why, what was tried, and what resulted. You can enter a note directly or import source material. GitHub is an optional connector; the core works without a repository or an external account.

`engineeringmemory.dev` is the working domain. This repository contains the first local prototype.

## Why a separate memory?

Commit messages and pull requests are good evidence about code changes. They often do not contain the decision before the change, an incident discussion, a failed attempt, or the outcome learned weeks later. Those details may live in different systems or only in someone's notes. Engineering Memory gives them a common, searchable form while retaining their origins and explicit relationships.

The memory does not certify a claim. A directly entered note is labelled as such, even when it includes a reference URI. An imported source retains its link, but the link alone does not verify every interpretation of it. Attribution supplied by a caller is a claim, not authenticated identity.

## What the local prototype does

- Records **Event**, **Change**, **Decision**, **Rationale**, **Attempt**, and **Outcome** entries in SQLite.
- Preserves the original **Source** (a note or imported artifact) and indexes searchable **Concepts** derived from explicit content. No model invents a reason or result.
- Links entries explicitly with `explains`, `contradicts`, `resulted_in`, or `supersedes` and can show a linked rationale when a decision matches a query.
- Tracks `active`, `superseded`, and `retracted` state. Current search excludes superseded and retracted entries unless history is requested; a term matching only an older note can route to its active successor. Direct writes can use an idempotency key for safe retries.
- Keeps event time (`occurred_at`) separate from capture time (`captured_at`) and labels the origin and claimed author in results.
- Returns short search excerpts and bounded context for an agent; exposes the same functions over a local MCP stdio server.
- Optionally imports GitHub commits, pull requests, and issues. Future connectors can map Jira, Slack/Teams, incidents, transcripts, docs/ADRs, observability, and support systems into the same core.

Search uses SQLite FTS5 lexical matching. It can miss synonyms, implicit references, or relevant evidence whose words differ from the question. It does not judge whether an answer is true. `scope` filters queries but is **not** an authorization boundary; this prototype is for one trusted local user, not a shared team server.

## Get started

Requires Python 3.11 or newer. Use an installed Python 3.11+ executable in place of `python3.13` if needed:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[mcp]'
engineering-memory add Decision "Use SQLite for local memory" \
  --rationale "One local file keeps setup simple" \
  --scope engineering-memory
engineering-memory search "Why SQLite?" --scope engineering-memory
engineering-memory context "Why SQLite?" --scope engineering-memory
```

The decision and its rationale are stored together as one source, with an explicit `Rationale` section indexed separately. To record a rationale learned later, first save the decision's `source_id` from the `add` output, then link a new note:

```bash
engineering-memory add Rationale "The deployment has no database service" \
  --scope engineering-memory --related-to SOURCE_ID --relation explains
```

Replace `SOURCE_ID` with the actual ID printed by the earlier command. This relationship is explicit; two nearby notes are not assumed to be related. `engineering-memory source SOURCE_ID` shows the full record and its links.

For retries, pass `--idempotency-key KEY` to `add`. Reusing the same key with the same content returns the existing entry; reusing it for different content is an error. To revise a directly recorded note, use `supersede OLD_ID KIND TEXT --reason "..."`; to withdraw one, use `retract ID --reason "..."`. Search and context accept `--include-history` when previous states are relevant. Use `--author-kind` and `--author` to record claimed attribution, and `--occurred-at` only when the underlying event time is known. These fields are not identity verification.

To import GitHub data, run `engineering-memory ingest github owner/repo`. `GITHUB_TOKEN` is needed for private repositories or higher API limits. Importing is independent of direct capture and query. The default database is `~/.local/share/engineering-memory/memory.db`; `ENGINEERING_MEMORY_DB` or `--db` selects another path. The `mcp` command starts a long-running local stdio server for an MCP client:

```bash
engineering-memory mcp
```

An MCP client can launch it as a local stdio server. For clients that accept a `mcpServers` JSON map, a typical entry is:

```json
{
  "mcpServers": {
    "engineering-memory": {
      "command": "engineering-memory",
      "args": ["mcp"],
      "env": {"ENGINEERING_MEMORY_DB": "/absolute/path/to/memory.db"}
    }
  }
}
```

Use a database path available to the client process. The MCP tools can record, link, supersede, retract, search, assemble context, and inspect sources. A client granted write-tool access can change that local database.

If you used the earlier GitHub-specific prototype, select a new database file; that legacy schema is rejected. The newer source-neutral schema has a migration for its first local version. Keep database files out of Git and treat them as sensitive when they contain private material.

## Evidence and maturity

The included [six synthetic retrieval cases](evals/README.md) exercise links, corrections, conflict, unsupported questions, and long sources. They are regression checks, **not** proof of superior answer quality or state-of-the-art performance. The next gate is a held-out set of 30–50 real engineering questions with independently labelled evidence and time validity, compared under the same context budget against raw source search and Git/GitHub search for code-related questions. See the [evaluation plan](docs/mvp-plan.md).

## Design principles

1. **Source-neutral core:** GitHub is one adapter, not the schema.
2. **Evidence before synthesis:** keep the source, timestamp, attribution, and relationship with each retrieved claim; leave unsupported questions unanswered.
3. **Explicit lifecycle:** preserve corrections and retractions instead of silently overwriting a note.
4. **Small local first loop:** one Python package, SQLite, FTS5, CLI, and MCP stdio; add more infrastructure only when measured needs justify it.

## Documentation

- [Vision and scope](docs/vision.md)
- [Architecture and data model](docs/architecture.md)
- [MVP and evaluation plan](docs/mvp-plan.md)
- [Contributing](CONTRIBUTING.md)

## License

MIT. See [LICENSE](LICENSE).
