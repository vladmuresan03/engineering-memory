# MVP architecture

Engineering Memory is a Python 3.11+ local application backed by SQLite and FTS5. The application service owns validation, writes, search, and context assembly. The CLI and MCP stdio server call that same service. An optional connector translates external items into the source-neutral model.

```text
direct note ──────────────┐
                         ├──> Source + explicit Links ──> SQLite
source adapter ───────────┘              │                   │
                                        └──> Concepts ──> FTS5 index
                                                               │
                                       CLI / MCP <── search + context
```

## Data model

**Source** is the stored origin or artifact: a directly recorded note, commit, PR, issue, incident, document, or message. It keeps the full title/body and provenance. **Concept** is a typed, searchable projection from that source. A source has a base concept with its declared kind and may have more concepts from explicit Markdown sections such as `## Rationale`. A fenced code example is not interpreted as a section. Derived concepts point back to the original source; they are not separate verified facts.

| Field | Meaning |
| --- | --- |
| `source_id` | Stable ID. Direct entries use a local ID; adapters should derive one from the external item. |
| `title`, `body` | Full stored content. Search returns excerpts; source inspection returns the full record. |
| `memory_kind` | Declared base kind: Event, Change, Decision, Rationale, Attempt, or Outcome. |
| `scope` | Caller-chosen project or team filter. It does not enforce access control. |
| `source_system`, `source_type`, `uri` | Origin, native artifact type, and optional locator. A URI is a reference, not proof. |
| `occurred_at` | Optional caller/source-supplied event time; unknown by default for direct notes. |
| `captured_at`, `indexed_at` | Local capture time and last index time; a retrospective event is not assigned its capture time as event time. |
| `author_kind`, `author` | Claimed human, agent, connector, or unknown attribution. No identity verification. |
| `state` | Active, superseded, or retracted. Default search uses active entries. |
| `metadata` | Connector details and direct-write metadata, including capture channel and optional idempotency key. |

The six kinds describe different claims. A `Change` is a concrete modification, an `Attempt` is an approach tried, and an `Outcome` is a reported or observed result; one must not be silently recast as another. A decision does not gain an inferred rationale merely because a related code change exists.

## Explicit relationships and lifecycle

Links join source IDs in the same scope. The direction is significant:

| Relation | Direction | Example |
| --- | --- | --- |
| `explains` | Reason → item explained | Rationale explains Decision |
| `resulted_in` | Antecedent → Outcome | Attempt resulted in Outcome |
| `contradicts` | Claim → conflicting claim | Proposal B contradicts Proposal A |
| `supersedes` | New record → previous record | Revised Decision supersedes old Decision |

The CLI and service can add links at record time or between existing records. A direct note can supersede another active direct note; it cannot overwrite imported evidence. Superseding retains the previous record, marks it `superseded`, and requires a change reason. Retraction retains a directly recorded note with a withdrawal reason. Default retrieval hides superseded and retracted records; history can be requested explicitly. Contradiction records a conflict, not a resolved winner.

Direct writes may include an idempotency key. Repeating the same write under the same key returns the existing ID; a different payload under that key is rejected. This prevents a transport retry from looking like independent corroboration. Distinct keys do not perform semantic duplicate detection. Imported records use stable external IDs for upsert, but deletion and permission changes are not yet synchronized.

These links are deliberately narrower than a full knowledge graph. They apply to whole sources, so a long artifact with several claims may need splitting or finer-grained linking later. The provenance model takes inspiration from [W3C PROV](https://www.w3.org/TR/prov-o/)'s distinction between entities and agents, but this implementation does not claim PROV-O compliance.

## Retrieval and context

[SQLite FTS5](https://www.sqlite.org/fts5.html) indexes concept text and provides lexical ranking and match snippets. Search applies scope and active-state filters, a conservative query-term coverage gate, and an output limit. It returns short excerpts plus source ID, kind, origin, claimed attribution, state, timestamps, and optional URI. A caller can inspect the full source by ID.

Context assembly fits results within a requested character budget. It prefers a focused explicit concept over a duplicate full-source hit and can add a linked rationale or outcome when space permits. When a query matches a superseded note, current search can return its active successor with the route and change reason labelled. It labels direct notes as not independently verified and treats retrieved content as data, not instructions. A no-match response means the local lexical retrieval found no support; it does **not** prove that the fact is false or absent from all source systems.

Lexical matching misses paraphrases and implicit relations, while overlapping terms can return irrelevant results. Relationship traversal only follows links that were explicitly recorded. Better candidate generation, ranking, and answer verification require measured evaluation before adding models or vector infrastructure.

## Interfaces and connector boundary

- The CLI offers `add`, `link`, `supersede`, `retract`, `search`, `context`, and `source`, plus optional `ingest github` and `mcp`.
- The local MCP server exposes corresponding read and write tools over stdio. MCP is an interface for clients to call tools; the protocol does not turn the local database into a hosted multi-user service. See the [MCP server model](https://modelcontextprotocol.io/specification/draft/server/index).
- Adapters map native artifacts to `Source` records. They own authentication, pagination, source URLs, and update semantics. The core never requires a GitHub repository ID or token. Jira, Slack/Teams, incidents, transcripts, docs/ADRs, observability, and support can each be adapters later.

An MCP client with write-tool access can modify this local database. `scope` is a filter and cannot enforce tenant permissions. External content may include prompt injection or false claims, so context retains attribution and marks excerpts as untrusted. A future shared service needs explicit identity, authorization, deletion propagation, and audit design.

## Storage and migration

The default path is `~/.local/share/engineering-memory/memory.db`; `ENGINEERING_MEMORY_DB` or `--db` overrides it. New local database files and their newly created private directory use restrictive permissions. Existing parent directories and existing files may have other permissions; operators should inspect paths holding sensitive data.

The current source-neutral schema supports migration from its first local version. The earlier GitHub-specific prototype has an incompatible schema and is rejected with an error; select a new file and preserve the old one if its data matters. This is a local prototype, with no hosted sync or general migration framework yet.
