# Retrieval evaluation seed

Run from the repository root after installing the package (`pip install -e .`):

```bash
python -m evals.run
python -m evals.run --json
python -m evals.run --strict
```

The runner creates a fresh temporary SQLite database, ingests the fixed records in `fixtures.py`, writes three direct records with links and idempotency keys, asks six task-shaped questions, and deletes the database. It never calls an LLM or an external service. Source aliases and required evidence phrases are hand-labelled in the fixture; direct records receive deterministic IDs from their idempotency keys. The default limits are five search matches and 1,200 context characters.

| Case | What it checks |
| --- | --- |
| `separate-rationale` | A decision and its rationale live in separate linked records; the rationale omits the decision's keyword. |
| `attempt-outcome` | The outcome survives retrieval when the query matches an attempt. |
| `superseded-decision` | A newer decision is preferred and the superseded one stays out of the current answer. |
| `unresolved-conflict` | Both opposing proposals appear as evidence; the system must not invent a resolution. |
| `absent-with-overlap` | Lexically similar records do not justify an answer to an unsupported question. |
| `long-source` | Relevant evidence at the end of a long artifact reaches a bounded context packet and search output stays concise. |

The report includes distinct-source recall@5 and precision among returned sources, source references visible in context, required evidence phrase coverage, whether an unsupported query gets the `No supporting memory found.` response, freshness checks, and output length bounds. For `separate-rationale`, raw search only needs to find the decision; context assembly must follow its explicit link and include the rationale. `--strict` returns a failing exit code if any case misses its explicit expectations; the ordinary run is diagnostic and always exits successfully. `--json` is suitable for comparing runs. The pass gate checks required evidence and exclusions; precision is reported separately to make irrelevant results visible even when a case passes.

**Interpretation:** These fixtures reveal regressions and obvious gaps, but cannot establish answer accuracy or state-of-the-art performance. In particular, the no-support check measures retrieval behavior, not whether a generated answer actually abstains. The expected phrases are exact strings, so the evaluation may penalize a valid paraphrase. Search matches can include several concepts from one source, so recall is computed over distinct source IDs. The set is small and synthetic; do not tune the product solely to these six cases.

Before claiming production quality, collect a held-out, permissioned corpus of real tasks and source records. Have people label relevant evidence, time validity, unresolved conflicts, and acceptable abstentions independently of the retrieval implementation. Compare against Git search and a simple document search baseline on the same tasks, and measure answer support, freshness, latency, cost, and privacy boundaries. Keep evaluation data out of the public repository unless it is explicitly cleared for publication.
