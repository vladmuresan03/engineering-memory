"""Run the fixture-based evidence retrieval benchmark.

Usage: python -m evals.run [--json] [--strict]
"""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from engineering_memory.service import Memory

from .fixtures import CASES, DIRECT_RECORDS, SCOPE, SOURCES, Case


DEFAULT_TOP_K = 5
DEFAULT_CONTEXT_CHARS = 1200
MAX_SEARCH_CONTENT_CHARS = 500


def _validate_fixtures() -> None:
    source_ids = [source.source_id for source in SOURCES]
    direct_aliases = [alias for alias, _ in DIRECT_RECORDS]
    case_ids = [case.case_id for case in CASES]
    if (
        len(set(source_ids + direct_aliases)) != len(source_ids) + len(direct_aliases)
        or len(set(case_ids)) != len(case_ids)
    ):
        raise ValueError("Fixture source IDs, direct aliases, and case IDs must be unique")
    known = set(source_ids + direct_aliases)
    for case in CASES:
        referenced = set(case.expected_source_ids + case.excluded_source_ids)
        if case.expected_search_source_ids is not None:
            referenced.update(case.expected_search_source_ids)
        if case.expected_first_source_id:
            referenced.add(case.expected_first_source_id)
        unknown = referenced - known
        if unknown:
            raise ValueError(f"{case.case_id}: unknown source IDs: {sorted(unknown)}")
        if set(case.expected_source_ids) & set(case.excluded_source_ids):
            raise ValueError(f"{case.case_id}: source cannot be both expected and excluded")


def _score_case(
    memory: Memory,
    case: Case,
    top_k: int,
    context_chars: int,
    id_to_alias: dict[str, str],
    reference_uris: dict[str, str],
) -> dict[str, Any]:
    matches = memory.search(case.question, scope=SCOPE, limit=top_k)
    ranked_ids = list(dict.fromkeys(id_to_alias.get(item["source_id"], item["source_id"]) for item in matches))
    context = memory.context(case.question, scope=SCOPE, max_chars=context_chars)
    expected = set(case.expected_source_ids)
    search_expected = set(
        case.expected_search_source_ids
        if case.expected_search_source_ids is not None else case.expected_source_ids
    )
    found = set(ranked_ids)
    excluded = set(case.excluded_source_ids)
    context_sources = {
        alias
        for alias, uri in reference_uris.items()
        if f"Reference: {json.dumps(uri, ensure_ascii=False)}" in context
    }
    evidence_found = [
        phrase for phrase in case.required_context_phrases if phrase.casefold() in context.casefold()
    ]
    max_search_content = max((len(item["content"]) for item in matches), default=0)
    abstained = not matches and "No supporting memory found." in context
    recall = len(search_expected & found) / len(search_expected) if search_expected else None
    precision = len(expected & found) / len(found) if found else (1.0 if not expected else 0.0)
    context_source_recall = (
        len(expected & context_sources) / len(expected) if expected else None
    )
    evidence_recall = (
        len(evidence_found) / len(case.required_context_phrases)
        if case.required_context_phrases else None
    )
    top_source_correct = (
        ranked_ids[0] == case.expected_first_source_id
        if case.expected_first_source_id else None
    )
    stale_or_excluded = sorted(excluded & (found | context_sources))
    bounded_context = len(context) <= context_chars
    bounded_search = max_search_content <= MAX_SEARCH_CONTENT_CHARS
    if case.expects_abstention:
        passed = abstained and bounded_context and bounded_search
    else:
        passed = (
            recall == 1
            and context_source_recall == 1
            and evidence_recall in (None, 1)
            and top_source_correct in (None, True)
            and not stale_or_excluded
            and bounded_context
            and bounded_search
        )
    return {
        "case_id": case.case_id,
        "description": case.description,
        "expected_source_ids": list(case.expected_source_ids),
        "expected_search_source_ids": sorted(search_expected),
        "returned_source_ids": ranked_ids,
        "context_source_ids": sorted(context_sources),
        "excluded_sources_returned": stale_or_excluded,
        "recall_at_k": recall,
        "source_precision_among_returned": precision,
        "irrelevant_source_ids": sorted(found - expected),
        "context_source_recall": context_source_recall,
        "context_evidence_recall": evidence_recall,
        "missing_context_phrases": [
            phrase for phrase in case.required_context_phrases if phrase not in evidence_found
        ],
        "top_source_correct": top_source_correct,
        "abstained": abstained if case.expects_abstention else None,
        "context_chars": len(context),
        "context_bounded": bounded_context,
        "max_search_content_chars": max_search_content,
        "search_content_bounded": bounded_search,
        "passed": passed,
    }


def evaluate(top_k: int = DEFAULT_TOP_K, context_chars: int = DEFAULT_CONTEXT_CHARS) -> dict[str, Any]:
    if top_k < 1 or context_chars < 300:
        raise ValueError("top_k must be positive and context_chars must be at least 300")
    _validate_fixtures()
    with TemporaryDirectory(prefix="engineering-memory-eval-") as directory:
        memory = Memory(Path(directory) / "memory.db")
        ingest = memory.ingest(SOURCES)
        id_to_alias = {source.source_id: source.source_id for source in SOURCES}
        alias_to_id = {source.source_id: source.source_id for source in SOURCES}
        reference_uris = {source.source_id: source.uri for source in SOURCES if source.uri}
        for alias, arguments in DIRECT_RECORDS:
            resolved = dict(arguments)
            for field in ("related_to", "supersedes"):
                if resolved.get(field) in alias_to_id:
                    resolved[field] = alias_to_id[resolved[field]]
            recorded = memory.record(**resolved)
            alias_to_id[alias] = recorded["source_id"]
            id_to_alias[recorded["source_id"]] = alias
            reference_uris[alias] = arguments["source_uri"]
        cases = [
            _score_case(memory, case, top_k, context_chars, id_to_alias, reference_uris)
            for case in CASES
        ]
    answerable = [case for case in cases if case["recall_at_k"] is not None]
    absent = [case for case in cases if case["abstained"] is not None]
    mean = lambda values: round(sum(values) / len(values), 3) if values else None
    return {
        "fixture": "synthetic diagnostic cases; not a SOTA benchmark",
        "settings": {
            "top_k": top_k,
            "context_chars": context_chars,
            "max_search_content_chars": MAX_SEARCH_CONTENT_CHARS,
        },
        "ingested": ingest,
        "direct_records": len(DIRECT_RECORDS),
        "summary": {
            "cases_passed": sum(case["passed"] for case in cases),
            "cases_total": len(cases),
            "mean_recall_at_k": mean([case["recall_at_k"] for case in answerable]),
            "mean_source_precision_among_returned": mean(
                [case["source_precision_among_returned"] for case in answerable]
            ),
            "mean_context_source_recall": mean(
                [case["context_source_recall"] for case in answerable]
            ),
            "mean_context_evidence_recall": mean(
                [case["context_evidence_recall"] for case in answerable
                 if case["context_evidence_recall"] is not None]
            ),
            "absent_cases_abstained": sum(case["abstained"] for case in absent),
            "absent_cases_total": len(absent),
            "bounded_context_cases": sum(case["context_bounded"] for case in cases),
            "bounded_search_cases": sum(case["search_content_bounded"] for case in cases),
        },
        "cases": cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--context-chars", type=int, default=DEFAULT_CONTEXT_CHARS)
    parser.add_argument("--json", action="store_true", help="print machine-readable results")
    parser.add_argument("--strict", action="store_true", help="exit nonzero if any case fails")
    args = parser.parse_args(argv)
    report = evaluate(args.top_k, args.context_chars)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for case in report["cases"]:
            marker = "PASS" if case["passed"] else "FAIL"
            print(f"{marker:4} {case['case_id']}: returned={case['returned_source_ids']}")
            if not case["passed"]:
                print(
                    f"     recall@{args.top_k}={case['recall_at_k']} "
                    f"context_source_recall={case['context_source_recall']} "
                    f"context_evidence_recall={case['context_evidence_recall']} "
                    f"abstained={case['abstained']} "
                    f"excluded={case['excluded_sources_returned']} "
                    f"max_search_chars={case['max_search_content_chars']}"
                )
        print(f"Summary: {report['summary']['cases_passed']}/{report['summary']['cases_total']} cases passed")
    return int(args.strict and report["summary"]["cases_passed"] != report["summary"]["cases_total"])


if __name__ == "__main__":
    raise SystemExit(main())
