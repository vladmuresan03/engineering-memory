"""Source-neutral records accepted by the memory index."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


ConceptKind = Literal["Event", "Change", "Decision", "Rationale", "Attempt", "Outcome"]
CONCEPT_KINDS = ("Event", "Change", "Decision", "Rationale", "Attempt", "Outcome")
AuthorKind = Literal["human", "agent", "connector", "unknown"]
AUTHOR_KINDS = ("human", "agent", "connector", "unknown")


def normalize_timestamp(value: str | None) -> str | None:
    """Require an offset-aware timestamp and store it in UTC."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("occurred_at must be an ISO 8601 timestamp with timezone")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("occurred_at must be an ISO 8601 timestamp with timezone") from error
    if parsed.tzinfo is None:
        raise ValueError("occurred_at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Source:
    """A record from any origin, including a directly entered note.

    ``uri`` is optional and is a reference supplied by the origin. It does not
    imply that Engineering Memory fetched or independently verified the URI.
    """

    source_id: str
    title: str
    body: str
    source_system: str = "manual"
    source_type: str = "note"
    scope: str | None = None
    uri: str | None = None
    occurred_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    memory_kind: ConceptKind = "Event"
    # An adapter may keep draft/proposal sections as searchable source text
    # without promoting their headings into typed memory concepts.
    promote_sections: bool = True
    # Attribution describes who supplied the record. It is a claim by the
    # caller/connector, not an authenticated identity.
    author_kind: AuthorKind = "connector"
    author: str | None = None


@dataclass(frozen=True, slots=True)
class Concept:
    """A typed observation linked to the record from which it was indexed."""

    source_id: str
    kind: ConceptKind
    content: str
    ordinal: int
