const examples = {
  sqlite: {
    question: "Why SQLite?",
    entries: [
      {
        kind: "DECISION",
        state: "CURRENT",
        title: "Use SQLite for the local MVP",
        detail: "One local database keeps the first release easy to run and inspect.",
        sourceId: "manual:demo-sqlite",
        origin: "DIRECT NOTE",
        captured: "2026-09-20",
        attribution: "UNATTRIBUTED",
      },
      {
        kind: "RATIONALE",
        state: "SAME SOURCE",
        detail: "A single file keeps setup and backups simple for a local prototype.",
        sourceId: "manual:demo-sqlite",
        origin: "DIRECT NOTE",
        captured: "2026-09-20",
        attribution: "UNATTRIBUTED",
        linked: true,
      },
    ],
  },
  queue: {
    question: "What replaced Redis?",
    entries: [
      {
        kind: "DECISION",
        state: "CURRENT",
        title: "Use a local task queue",
        detail: "The replacement keeps development self-contained while task volume is small.",
        sourceId: "manual:demo-queue",
        origin: "DIRECT NOTE",
        captured: "2026-09-20",
        attribution: "UNATTRIBUTED",
      },
      {
        kind: "RATIONALE",
        state: "EXPLAINS DECISION",
        detail: "Operating a separate Redis service added complexity before the workload required it.",
        sourceId: "manual:demo-queue-why",
        origin: "DIRECT NOTE",
        captured: "2026-09-21",
        attribution: "UNATTRIBUTED",
        linked: true,
      },
    ],
  },
  retries: {
    question: "What did we learn from retries?",
    entries: [
      {
        kind: "ATTEMPT",
        state: "RECORDED",
        title: "Retry every failed request",
        detail: "A broad retry rule was tried during an incident response.",
        sourceId: "manual:demo-retry-attempt",
        origin: "INCIDENT NOTE",
        captured: "2026-09-20",
        attribution: "UNATTRIBUTED",
      },
      {
        kind: "OUTCOME",
        state: "RESULTED FROM ATTEMPT",
        detail: "Repeated permanent failures increased load. Later work limited retries to transient errors.",
        sourceId: "manual:demo-retry-outcome",
        origin: "INCIDENT NOTE",
        captured: "2026-09-21",
        attribution: "UNATTRIBUTED",
        linked: true,
      },
    ],
  },
};

const buttons = document.querySelectorAll(".question-button");
const packetQuery = document.getElementById("packet-query");
const packetItems = document.getElementById("packet-items");

function makeEntry(entry) {
  const card = document.createElement("article");
  card.className = `evidence-card${entry.linked ? " evidence-card-linked" : ""}`;

  const head = document.createElement("div");
  head.className = "evidence-head";
  const kind = document.createElement("span");
  kind.className = `kind kind-${entry.kind.toLowerCase()}`;
  kind.textContent = entry.kind;
  const state = document.createElement("span");
  state.className = entry.linked ? "evidence-relation" : "evidence-state";
  state.textContent = entry.state;
  head.append(kind, state);
  card.append(head);

  if (entry.title) {
    const title = document.createElement("h3");
    title.textContent = entry.title;
    card.append(title);
  }

  const detail = document.createElement("p");
  detail.textContent = entry.detail;
  card.append(detail);

  const meta = document.createElement("div");
  meta.className = "evidence-meta";
  const sourceLine = document.createElement("div");
  sourceLine.textContent = `SOURCE ID: ${entry.sourceId}`;
  const sourceSeparator = document.createElement("span");
  sourceSeparator.textContent = "·";
  sourceLine.append(sourceSeparator, document.createTextNode(entry.origin));
  const capturedLine = document.createElement("div");
  capturedLine.textContent = `CAPTURED: ${entry.captured}`;
  const capturedSeparator = document.createElement("span");
  capturedSeparator.textContent = "·";
  capturedLine.append(capturedSeparator, document.createTextNode(entry.attribution));
  meta.append(sourceLine, capturedLine);
  card.append(meta);

  return card;
}

for (const button of buttons) {
  button.addEventListener("click", () => {
    const example = examples[button.dataset.example];
    if (!example) return;

    for (const other of buttons) {
      const active = other === button;
      other.classList.toggle("is-active", active);
      other.setAttribute("aria-pressed", String(active));
    }

    packetQuery.textContent = example.question;
    packetItems.replaceChildren(...example.entries.map(makeEntry));
  });
}
