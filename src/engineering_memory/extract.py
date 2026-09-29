"""Conservative, deterministic concept extraction from generic records."""

import re

from .models import CONCEPT_KINDS, Concept, ConceptKind, Source


HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
HEADING_KIND: dict[str, ConceptKind] = {
    "event": "Event",
    "change": "Change",
    "changes": "Change",
    "implementation": "Change",
    "decision": "Decision",
    "decisions": "Decision",
    "rationale": "Rationale",
    "why": "Rationale",
    "motivation": "Rationale",
    "attempt": "Attempt",
    "attempts": "Attempt",
    "tried": "Attempt",
    "experiment": "Attempt",
    "experiments": "Attempt",
    "outcome": "Outcome",
    "result": "Outcome",
    "results": "Outcome",
    "impact": "Outcome",
}


def extract_concepts(source: Source) -> list[Concept]:
    """Index the artifact and only label explicit Markdown sections as claims.

    The input sets its own base memory kind. A heading such as ``## Decision``
    is required before an imported document section is called a Decision.
    """
    if not source.source_id.strip() or not source.title.strip():
        raise ValueError("source_id and title are required")
    if source.memory_kind not in CONCEPT_KINDS:
        raise ValueError(f"invalid memory_kind: {source.memory_kind}")

    body = source.body or ""
    base_text = "\n\n".join(part for part in (source.title.strip(), body.strip()) if part)
    concepts = [Concept(source.source_id, source.memory_kind, base_text, 0)]
    if not source.promote_sections:
        return concepts

    current_kind: ConceptKind | None = None
    section_lines: list[str] = []

    def flush() -> None:
        nonlocal section_lines
        text = "\n".join(section_lines).strip()
        if current_kind is not None and text:
            concepts.append(Concept(source.source_id, current_kind, text, len(concepts)))
        section_lines = []

    fence_char: str | None = None
    fence_length = 0
    for line in body.splitlines():
        if fence_char is not None:
            section_lines.append(line)
            # A closing fence uses the same marker, at least as many times,
            # and contains only whitespace after it.
            if re.fullmatch(
                rf" {{0,3}}{re.escape(fence_char)}{{{fence_length},}}[ \t]*", line
            ):
                fence_char = None
                fence_length = 0
            continue

        opening = FENCE_OPEN.match(line)
        if opening and (opening.group(1)[0] != "`" or "`" not in opening.group(2)):
            fence_char = opening.group(1)[0]
            fence_length = len(opening.group(1))
            section_lines.append(line)
            continue

        match = HEADING.match(line)
        if match:
            flush()
            key = match.group(1).strip().lower().rstrip(":")
            current_kind = HEADING_KIND.get(key)
        else:
            section_lines.append(line)
    flush()
    return concepts
