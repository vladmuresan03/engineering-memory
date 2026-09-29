# Contributing

Engineering Memory is an early open-source project. Contributions to capture, provenance, retrieval, evaluation, connector reliability, examples, and documentation are welcome. The design goal is trustworthy, source-neutral engineering context; performance claims need held-out evidence.

## Before you change code

Read the [vision](docs/vision.md) and [architecture](docs/architecture.md). Open an issue for a substantial design change so the problem and expected behavior are clear. A focused pull request can proceed directly, with a short explanation and a realistic example when storage or retrieval behavior changes.

## Local development

Use Python 3.11 or newer. Replace `python3.13` with any installed Python 3.11+ executable if needed:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[mcp,dev]'
python -m pytest
python -m evals.run --strict
```

Do not commit tokens, database files, private notes, or private imported content. Use synthetic fixtures or material safe to redistribute.

## Working agreements

- Keep the core record and retrieval model independent of any one connector.
- Keep full source artifacts separate from searchable concept projections. Show whether a record was entered directly or imported, and preserve an available source URI without treating it as independent verification.
- Distinguish event time from capture time, and show correction state and claimed attribution without presenting them as verified identity.
- Do not infer a decision, reason, or outcome from a change unless the evidence says so.
- Keep connector authentication and native object shapes at the adapter boundary.
- Add tests for behavior changes, including stale or conflicting evidence when relevant, and document user-visible commands or configuration changes.
- Use the synthetic evaluation suite as a regression check. Claims that retrieval is better than Git or raw source search need the held-out comparison in the [MVP plan](docs/mvp-plan.md).
- State tradeoffs and limitations plainly in a pull request.

By contributing, you agree that your contribution is licensed under the project's [MIT License](LICENSE).
