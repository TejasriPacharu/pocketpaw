# ee/widget_suggestions/detector.py — Find co-occurring query patterns.
# Created: 2026-04-13 (Move 8 PR-B) — Lean detector that reads the
# retrieval log written by ee/retrieval (Move 4 PR-B), groups consecutive
# queries from the same actor, and surfaces pairs that repeat above a
# threshold within a window. The agent uses these as input to propose
# new widgets via the existing Instinct propose flow.

from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from ee.widget_suggestions.models import (
    PatternMatch,
    SuggestedWidget,
    SuggestionReport,
)

logger = logging.getLogger(__name__)


DEFAULT_WINDOW_DAYS = 7
DEFAULT_THRESHOLD = 3
_SESSION_GAP = timedelta(minutes=15)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


async def detect_co_occurrence_patterns(
    log: Any,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    threshold: int = DEFAULT_THRESHOLD,
    pocket_id: str | None = None,
) -> SuggestionReport:
    """Scan the retrieval log and surface SuggestedWidget proposals.

    Two queries co-occur when the same actor runs them inside the same
    "session" — defined here as queries less than 15 minutes apart in the
    same pocket. A pair that recurs ``threshold`` times in the window
    earns a SuggestedWidget. ``log`` must satisfy the ee.retrieval
    RetrievalLog read shape (``read(pocket_id, since, limit)``).
    """
    since = datetime.now() - timedelta(days=window_days)
    entries = await log.read(pocket_id=pocket_id, since=since, limit=20_000)

    sessions = _group_into_sessions(entries)

    pair_counts: dict[str, int] = defaultdict(int)
    pair_meta: dict[str, dict[str, Any]] = {}

    for session in sessions:
        for pair in _unordered_pairs(session):
            sig = _signature(pair)
            if not sig:
                continue
            pair_counts[sig] += 1
            meta = pair_meta.setdefault(
                sig,
                {
                    "queries": [str(p.get("query", "")) for p in pair],
                    "actors": [],
                    "pocket_id": None,
                },
            )
            actor = pair[0].get("actor", "")
            if actor and actor not in meta["actors"]:
                meta["actors"].append(actor)
            if not meta["pocket_id"] and pair[0].get("pocket_id"):
                meta["pocket_id"] = pair[0]["pocket_id"]

    suggestions: list[SuggestedWidget] = []
    for sig, count in pair_counts.items():
        if count < threshold:
            continue
        meta = pair_meta[sig]
        match = PatternMatch(
            signature=sig,
            queries=meta["queries"],
            count=count,
            pocket_id=meta["pocket_id"],
            recent_actors=meta["actors"][:5],
        )
        suggestions.append(
            SuggestedWidget(
                id=f"sw_{sig[:12]}",
                pocket_id=meta["pocket_id"],
                title=_title_for(meta["queries"]),
                description=(
                    f"Detected {count} co-occurrences in the last "
                    f"{window_days} days. A side-by-side widget would "
                    "answer both queries in one glance."
                ),
                widget_type="list",
                pattern=match,
                confidence=min(1.0, count / (threshold * 3)),
            ),
        )

    return SuggestionReport(
        suggestions=suggestions,
        scanned_traces=len(entries),
        window_days=window_days,
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _group_into_sessions(entries: list[Any]) -> list[list[dict[str, Any]]]:
    """Group retrieval log entries into per-actor + per-pocket sessions."""
    sorted_entries = sorted(entries, key=lambda e: _entry_timestamp(e))
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in sorted_entries:
        actor = _entry_attr(entry, "actor") or ""
        pocket = _entry_attr(entry, "pocket_id") or ""
        by_key[(actor, pocket)].append(_entry_to_payload(entry))

    sessions: list[list[dict[str, Any]]] = []
    for items in by_key.values():
        if not items:
            continue
        current: list[dict[str, Any]] = [items[0]]
        for prev, curr in zip(items, items[1:], strict=False):
            if curr["timestamp"] - prev["timestamp"] <= _SESSION_GAP:
                current.append(curr)
            else:
                if len(current) > 1:
                    sessions.append(current)
                current = [curr]
        if len(current) > 1:
            sessions.append(current)
    return sessions


def _unordered_pairs(session: list[dict[str, Any]]) -> Iterable[list[dict[str, Any]]]:
    n = len(session)
    for i in range(n):
        for j in range(i + 1, n):
            yield [session[i], session[j]]


def _signature(pair: list[dict[str, Any]]) -> str:
    norm = sorted(_normalise_query(p.get("query", "")) for p in pair)
    norm = [n for n in norm if n]
    if len(norm) < 2 or norm[0] == norm[1]:
        return ""
    return "::".join(norm)


def _normalise_query(query: str) -> str:
    """Token bag with stable ordering so word-order variants collide.

    "renewal discount" and "discount renewal" are the same question phrased
    two ways — they should not produce a "side-by-side widget" suggestion.
    Sorting the token list makes both normalise to "discount renewal" and
    the duplicate-token check in :func:`_signature` then suppresses them.
    """
    tokens = _TOKEN_RE.findall(query.lower())
    return " ".join(sorted(tokens[:6]))


def _title_for(queries: list[str]) -> str:
    parts = [q[:30] for q in queries[:2]]
    return f"Suggested: {' + '.join(parts)}"


def _entry_attr(entry: Any, attr: str) -> Any:
    if hasattr(entry, attr):
        return getattr(entry, attr)
    if hasattr(entry, "trace") and isinstance(entry.trace, dict):
        return entry.trace.get(attr)
    if isinstance(entry, dict):
        return entry.get(attr)
    return None


def _entry_timestamp(entry: Any) -> datetime:
    raw = _entry_attr(entry, "timestamp")
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return datetime.min
    if hasattr(entry, "ingested_at"):
        return entry.ingested_at
    return datetime.min


def _entry_to_payload(entry: Any) -> dict[str, Any]:
    return {
        "actor": _entry_attr(entry, "actor") or "",
        "query": _entry_attr(entry, "query") or "",
        "pocket_id": _entry_attr(entry, "pocket_id"),
        "timestamp": _entry_timestamp(entry),
    }
