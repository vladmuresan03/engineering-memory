# MVP and evaluation plan

The goal is a useful local memory loop: capture a consequential engineering claim, retrieve it later with its origin and time, and show when it was corrected or disputed. The first release is intentionally source-neutral. GitHub is an optional adapter and a comparison baseline for code-related questions.

## Implemented local loop

1. **Capture:** direct `Event`, `Change`, `Decision`, `Rationale`, `Attempt`, or `Outcome` entry through CLI or MCP; optional title, scope, reference, claimed author, event time, and idempotency key.
2. **Preserve:** full `Source` record with capture time, origin, state, and explicit source-to-source links. Separate `Concept` projections from explicit content are indexed for search.
3. **Retrieve:** lexical FTS5 search, bounded snippets and context, linked evidence, full source inspection, current-state filtering, and an optional history view.
4. **Correct:** supersede an active direct record with a reason or retract a direct entry with a reason, retaining the older claim for inspection. When a stale term matches, route to its active successor and show why the record changed.
5. **Connect:** import GitHub artifacts using stable IDs without making GitHub required for any other workflow.

The [six synthetic cases](../evals/README.md) exercise linked rationale, attempt/outcome, supersession, unresolved conflict, unsupported questions, and long-source bounds. They are a deterministic regression suite, not a measured product advantage. A pass on six crafted cases is not a state-of-the-art claim.

## Release work still needed

- Verify the new CI workflow on GitHub for supported Python versions, tests, and the synthetic evaluation gate.
- Verify MCP tool inputs and outputs in a real client session; the README includes a generic stdio configuration.
- Add a source-neutral demo corpus with a few decisions, attempts, outcomes, corrections, and explicit links. Keep private material and tokens out of the repository.
- Exercise optional GitHub import on a public test repository and document update, deletion, closed-unmerged PR, rate-limit, and permission behavior precisely.
- Decide how a user inspects and repairs accidental links, and how source-level links should evolve when one artifact contains multiple claims.
- Publish an initial open-source release only after install, examples, and security checks are reproducible by a new contributor.

## Real-task evaluation gate

Before claiming that this is more useful than raw history, freeze a permissioned corpus and collect **30–50 held-out engineering questions** from actual work. Include questions about decisions and rationale, failed attempts, later outcomes, current versus superseded choices, contradictions, and facts absent from the corpus. Use data from more than one source when possible. A question set drawn only from this project's README or synthetic fixtures would leak the implementation's assumptions into the evaluation.

For each question, have a reviewer who did not build the retriever label: supporting source IDs and excerpts, when each claim was valid, whether evidence conflicts, and whether abstention is the right answer. Keep private corpora out of the public repository unless cleared for release. Preserve a reproducible public synthetic subset for contributors.

Compare at least these workflows on the **same corpus and context budget**:

| Workflow | Why it matters |
| --- | --- |
| Raw source keyword search | Tests whether structure and links add value beyond indexing all documents. |
| Git history / GitHub search for code questions | Tests the user's original commit-message alternative where it is applicable. |
| Engineering Memory without link expansion | Isolates the value of explicit relationships. |
| Engineering Memory with links and lifecycle | Measures the current design, including corrections and conflicts. |

If an answering model is used, hold its version, prompt, and token budget constant. Report retrieval and final-answer results separately: evidence recall@k and precision, answer support by cited sources, stale-answer rate, conflict handling, correct abstention, latency, context size, and human effort or tool calls. Show per-question failures, not only an aggregate score. Measure whether lifecycle and attribution actually help an agent avoid wrong actions. Repeat on a later held-out set before adding features based on a single result.

Public research provides useful failure categories, but its scores are not transferable to this project. [LongMemEval](https://arxiv.org/abs/2410.10813) evaluates long-term extraction, temporal reasoning, updates, and abstention in conversational assistants. [MemConflict](https://arxiv.org/abs/2605.20926) highlights the gap between retrieving memories and selecting contextually valid evidence under conflict. They motivate our questions; they do not validate this architecture. [SQLite FTS5](https://www.sqlite.org/fts5.html) documents the current lexical search mechanism and its snippets.

## Decisions after evidence

- Add semantic candidate generation only if held-out questions show a lexical recall gap large enough to justify its cost and maintenance.
- Add automated extraction only with a trace back to original text and a way to keep generated claims separate from source-authored ones.
- Add more connectors when real workflows identify valuable missing evidence, with sync, deletion, permission, and update policies for each.
- Design hosted sharing only after authentication, authorization, isolation, conflict resolution, and audit requirements are concrete.

The first architecture should make these changes possible without requiring them for a useful local prototype.
