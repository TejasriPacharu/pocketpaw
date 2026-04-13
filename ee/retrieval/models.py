# ee/retrieval/models.py — RetrievalLogEntry: the on-disk shape of one trace.
# Created: 2026-04-13 — Wraps the soul-protocol RetrievalTrace with the small
# amount of paw-runtime context the trace itself doesn't carry (host process,
# session, ingestion timestamp). Lean — no inheritance, just a thin wrapper.

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# Re-export for callers that already have a RetrievalTrace in hand.
try:
    from soul_protocol.spec.retrieval import RetrievalCandidate, RetrievalTrace
except ImportError:  # pragma: no cover — soul-protocol is required at runtime
    RetrievalTrace = None  # type: ignore[assignment]
    RetrievalCandidate = None  # type: ignore[assignment]


class RetrievalLogEntry(BaseModel):
    """One JSON line in ~/.pocketpaw/retrieval.jsonl.

    The trace itself is the soul-protocol primitive. The wrapper adds the
    paw-runtime context fields that aren't part of the portable spec — the
    process that wrote the trace, the session it belonged to, and the
    ingest timestamp. Append-only; never mutated after write.
    """

    trace: dict[str, Any]
    ingested_at: datetime = Field(default_factory=datetime.now)
    process: str = "paw-runtime"
    session_id: str | None = None

    def trace_id(self) -> str:
        return str(self.trace.get("id", ""))

    def actor(self) -> str:
        return str(self.trace.get("actor", ""))

    def source(self) -> str:
        return str(self.trace.get("source", ""))

    def query(self) -> str:
        return str(self.trace.get("query", ""))

    def pocket_id(self) -> str | None:
        value = self.trace.get("pocket_id")
        return str(value) if value else None

    def candidate_ids(self) -> list[str]:
        candidates = self.trace.get("candidates") or []
        return [str(c.get("id")) for c in candidates if c.get("id")]
