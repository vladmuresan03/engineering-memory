# Vision

Engineering Memory should help a person or AI coding agent answer engineering questions with concise, time-aware evidence:

- What happened and when?
- What changed or was decided, and why?
- Which approaches were tried or rejected?
- What outcome was observed later?
- Which claims are current, disputed, or withdrawn?

The working goal is **institutional memory**, not a second copy of Git history. Git commits and PRs are useful evidence for code changes. Decisions, constraints, failed attempts, incident findings, and later outcomes may be recorded elsewhere or directly by a teammate. The system should connect these records without pretending they all originated in Git.

## First useful loop

An engineer records a decision with its rationale under a project scope. A later agent asks why that decision was made. Engineering Memory returns a short passage containing the decision, rationale, original record ID, capture time, and claimed attribution. If the rationale was added later, the person or agent can link it explicitly. No GitHub setup is required.

A direct note remains a claim by its recorder. An imported artifact remains a claim or observation from its external system. Neither a source URI nor an agent-written summary independently verifies content. When evidence conflicts or is absent, the system should show that state rather than synthesize a confident answer.

## Product boundaries

- **Now:** one local SQLite database, direct capture, explicit links and correction states, lexical search, bounded context, MCP tools, and an optional GitHub adapter.
- **Later, if validated:** Jira, Slack/Teams, incidents, meeting transcripts, docs/ADRs, observability, and support adapters; deeper retrieval; team sharing and permissions.
- **Out of the first release:** a hosted multi-user service, automatic truth adjudication, automatic relation inference, and a generated canonical history.

`scope` is a query filter, not tenant isolation. The local process and its MCP client are assumed to be trusted with the database. A team service would need authentication, authorization, sync, deletion propagation, audit, and conflict policies before handling private shared memory.

## What success would mean

The prototype should reduce the effort to find relevant engineering evidence without increasing unsupported or stale answers. The six synthetic cases in this repository test known failure modes but do not demonstrate that benefit. A meaningful next test is a held-out set of 30–50 real questions with independently labelled supporting sources, temporal validity, and acceptable abstentions. Compare the same tasks against raw source search and Git/GitHub search where applicable, using the same context budget and recording answer support, retrieval quality, latency, and effort.

The aspiration is a memory system informed by current research, not a claim of state-of-the-art results. [LongMemEval](https://arxiv.org/abs/2410.10813) motivates tests for temporal reasoning, updates, and abstention; [MemConflict](https://arxiv.org/abs/2605.20926) motivates explicit tests for conflicting and context-dependent evidence. Both study conversational memory, so their findings are design prompts rather than direct evidence that this engineering-memory prototype works.
