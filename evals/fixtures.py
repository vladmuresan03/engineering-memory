"""Synthetic cases with hand-labelled evidence IDs and expected behavior.

These cases are deliberately small and diagnostic. They are not a substitute
for a held-out, human-labelled corpus from real engineering work.
"""

from dataclasses import dataclass

from engineering_memory.models import Source


SCOPE = "eval/checkout"


@dataclass(frozen=True)
class Case:
    case_id: str
    question: str
    expected_source_ids: tuple[str, ...] = ()
    expected_search_source_ids: tuple[str, ...] | None = None
    required_context_phrases: tuple[str, ...] = ()
    excluded_source_ids: tuple[str, ...] = ()
    expected_first_source_id: str | None = None
    description: str = ""

    @property
    def expects_abstention(self) -> bool:
        return not self.expected_source_ids


LONG_PRELUDE = ("Routine deployment checks completed without changes. " * 105).strip()

SOURCES = (
    Source(
        source_id="eval:storage-decision",
        title="Use SQLite for the local memory index",
        body="The first release stores memory in a local SQLite database.",
        source_system="adr",
        source_type="decision",
        scope=SCOPE,
        uri="https://evidence.example.test/storage/decision",
        occurred_at="2026-01-10T10:00:00Z",
        memory_kind="Decision",
    ),
    Source(
        source_id="eval:retry-incident",
        title="API retry experiment",
        body=(
            "## Attempt\nTried three retries on idempotent API requests.\n\n"
            "## Outcome\nTail latency rose; one retry reduced connection reset failures."
        ),
        source_system="incident",
        source_type="report",
        scope=SCOPE,
        uri="https://evidence.example.test/retry/incident",
        occurred_at="2026-02-03T14:00:00Z",
        memory_kind="Event",
    ),
    Source(
        source_id="eval:transport-kafka",
        title="Billing event transport proposal",
        body="## Decision\nUse Kafka for event delivery in the billing service.",
        source_system="meeting",
        source_type="minutes",
        scope=SCOPE,
        uri="https://evidence.example.test/transport/kafka",
        occurred_at="2026-06-01T10:00:00Z",
        memory_kind="Event",
    ),
    Source(
        source_id="eval:transport-nats",
        title="Billing event transport alternative",
        body="## Decision\nUse NATS for event delivery in the billing service.",
        source_system="ticket",
        source_type="proposal",
        scope=SCOPE,
        uri="https://evidence.example.test/transport/nats",
        occurred_at="2026-06-02T10:00:00Z",
        memory_kind="Event",
    ),
    Source(
        source_id="eval:rollback-runbook",
        title="Checkout routing rollback notes",
        body=(
            LONG_PRELUDE
            + "\n\n## Outcome\nRollback of the feature flag restored checkout routing in four minutes."
        ),
        source_system="incident",
        source_type="runbook",
        scope=SCOPE,
        uri="https://evidence.example.test/rollback/runbook",
        occurred_at="2026-07-04T08:00:00Z",
        memory_kind="Event",
    ),
    Source(
        source_id="eval:other-project-storage",
        title="Use MySQL for the local memory index",
        body="A different project chose MySQL for its local memory index.",
        source_system="adr",
        source_type="decision",
        scope="eval/other-project",
        uri="https://evidence.example.test/other-project/storage",
        occurred_at="2026-03-01T10:00:00Z",
        memory_kind="Decision",
    ),
)

# Stable fixture aliases map to the deterministic IDs returned by record().
# This uses the public write path for relationships and supersession.
DIRECT_RECORDS = (
    (
        "eval:storage-rationale",
        {
            "kind": "Rationale",
            "content": "One local file keeps deployment and backups simple for a single-developer MVP.",
            "title": "Single-file deployment rationale",
            "scope": SCOPE,
            "source_uri": "https://evidence.example.test/storage/rationale",
            "recorded_by": "eval-harness",
            "idempotency_key": "storage-rationale-v1",
            "occurred_at": "2026-01-10T10:05:00Z",
            "related_to": "eval:storage-decision",
            "relation": "explains",
        },
    ),
    (
        "eval:queue-old",
        {
            "kind": "Decision",
            "content": "Redis became the queue backend for checkout background jobs.",
            "title": "Use Redis as queue backend for checkout jobs",
            "scope": SCOPE,
            "source_uri": "https://evidence.example.test/queue/old",
            "recorded_by": "eval-harness",
            "idempotency_key": "queue-redis-v1",
            "occurred_at": "2026-01-15T10:00:00Z",
        },
    ),
    (
        "eval:queue-new",
        {
            "kind": "Decision",
            "content": "Postgres replaced Redis after worker failover lost queued jobs.",
            "title": "Use Postgres as queue backend for checkout jobs",
            "scope": SCOPE,
            "source_uri": "https://evidence.example.test/queue/new",
            "recorded_by": "eval-harness",
            "idempotency_key": "queue-postgres-v1",
            "occurred_at": "2026-05-20T09:00:00Z",
            "supersedes": "eval:queue-old",
            "change_reason": "Worker failover lost queued jobs.",
        },
    ),
)


CASES = (
    Case(
        case_id="separate-rationale",
        question="Why SQLite?",
        expected_source_ids=("eval:storage-decision", "eval:storage-rationale"),
        expected_search_source_ids=("eval:storage-decision",),
        required_context_phrases=("One local file keeps deployment and backups simple",),
        excluded_source_ids=("eval:other-project-storage",),
        description="A rationale is a separate, related record without the word SQLite.",
    ),
    Case(
        case_id="attempt-outcome",
        question="What happened after we tried three retries on API requests?",
        expected_source_ids=("eval:retry-incident",),
        required_context_phrases=("Tail latency rose",),
        description="Retrieval must preserve the outcome, not only the matching attempt.",
    ),
    Case(
        case_id="superseded-decision",
        question="What is the current queue backend for checkout jobs?",
        expected_source_ids=("eval:queue-new",),
        excluded_source_ids=("eval:queue-old",),
        expected_first_source_id="eval:queue-new",
        required_context_phrases=("Postgres replaced Redis",),
        description="A prior decision should not be presented as current.",
    ),
    Case(
        case_id="unresolved-conflict",
        question="Which event delivery system should the billing service use?",
        expected_source_ids=("eval:transport-kafka", "eval:transport-nats"),
        required_context_phrases=("Kafka", "NATS"),
        description="Both conflicting proposals should be visible, without invented resolution.",
    ),
    Case(
        case_id="absent-with-overlap",
        question="What is the SOC2 retention period for billing event delivery?",
        description="Shared words must not be mistaken for evidence of a retention policy.",
    ),
    Case(
        case_id="long-source",
        question="What did the checkout routing rollback restore?",
        expected_source_ids=("eval:rollback-runbook",),
        required_context_phrases=("restored checkout routing in four minutes",),
        description="An answer near the end of a long artifact must survive context trimming.",
    ),
)
