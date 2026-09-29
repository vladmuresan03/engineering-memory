"""Markdown headings only make claims when they are outside code fences."""

import pytest

from engineering_memory.extract import extract_concepts
from engineering_memory.models import Source


@pytest.mark.parametrize("marker", ["```", "~~~~"])
def test_headings_inside_code_fences_are_not_memory_claims(marker: str) -> None:
    body = (
        "## Decision\nUse SQLite for the first version.\n"
        f"{marker}markdown\n"
        "## Rationale\nThis is an example, not our rationale.\n"
        f"{marker}\n"
        "## Rationale\nA local file keeps setup simple."
    )
    concepts = extract_concepts(Source(source_id="doc:1", title="Storage", body=body))

    assert [concept.kind for concept in concepts] == ["Event", "Decision", "Rationale"]
    assert concepts[1].content == (
        "Use SQLite for the first version.\n"
        f"{marker}markdown\n"
        "## Rationale\nThis is an example, not our rationale.\n"
        f"{marker}"
    )
    assert concepts[2].content == "A local file keeps setup simple."


def test_longer_fence_ignores_shorter_marker_and_headings_until_real_close() -> None:
    body = (
        "~~~~~markdown\n"
        "## Decision\nExample decision.\n"
        "~~~~\n"
        "## Outcome\nStill inside the example.\n"
        "~~~~~\n"
        "## Outcome\nThe migration succeeded."
    )
    concepts = extract_concepts(Source(source_id="doc:2", title="Migration", body=body))

    assert [concept.kind for concept in concepts] == ["Event", "Outcome"]
    assert concepts[1].content == "The migration succeeded."


def test_unclosed_fence_does_not_create_claims_from_example() -> None:
    body = "```markdown\n## Decision\nOnly an example"
    concepts = extract_concepts(Source(source_id="doc:3", title="Notes", body=body))

    assert [concept.kind for concept in concepts] == ["Event"]
