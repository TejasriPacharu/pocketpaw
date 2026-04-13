# tests/cloud/test_widget_suggestions.py — Move 8 PR-B.
# Created: 2026-04-13 — Co-occurrence detector behaviour: session boundary
# enforcement (15-min gap), threshold semantics, signature dedup,
# pocket/actor isolation, output shape.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pytest

from ee.widget_suggestions.detector import (
    DEFAULT_THRESHOLD,
    detect_co_occurrence_patterns,
)


@dataclass
class _FakeEntry:
    """Lightweight stand-in for a retrieval log entry."""

    actor: str
    query: str
    pocket_id: str | None
    timestamp: datetime
    trace: dict[str, Any] = field(default_factory=dict)


class _FakeLog:
    """Test double — exposes the read() shape the detector consumes."""

    def __init__(self, entries: list[_FakeEntry]) -> None:
        self._entries = entries

    async def read(
        self,
        *,
        pocket_id: str | None = None,
        since: datetime | None = None,
        limit: int = 20_000,
    ) -> list[_FakeEntry]:
        rows = self._entries
        if pocket_id is not None:
            rows = [e for e in rows if e.pocket_id == pocket_id]
        if since is not None:
            rows = [e for e in rows if e.timestamp >= since]
        return rows[:limit]


def _entry(
    *,
    actor: str = "user:priya",
    query: str = "renewal discount",
    pocket_id: str | None = "pocket-1",
    when: datetime | None = None,
) -> _FakeEntry:
    return _FakeEntry(
        actor=actor,
        query=query,
        pocket_id=pocket_id,
        timestamp=when or datetime.now(),
    )


# ---------------------------------------------------------------------------
# Threshold + co-occurrence
# ---------------------------------------------------------------------------


class TestCoOccurrence:
    @pytest.mark.asyncio
    async def test_repeated_pair_above_threshold_yields_suggestion(self) -> None:
        base = datetime.now() - timedelta(hours=1)
        entries: list[_FakeEntry] = []
        for i in range(DEFAULT_THRESHOLD):
            session_start = base + timedelta(hours=i)
            entries.append(_entry(query="acme deal status", when=session_start))
            entries.append(
                _entry(query="acme renewal date", when=session_start + timedelta(minutes=2)),
            )

        report = await detect_co_occurrence_patterns(_FakeLog(entries))
        assert len(report.suggestions) == 1
        suggestion = report.suggestions[0]
        assert suggestion.pattern.count >= DEFAULT_THRESHOLD
        assert suggestion.title.startswith("Suggested:")

    @pytest.mark.asyncio
    async def test_pair_below_threshold_not_suggested(self) -> None:
        base = datetime.now() - timedelta(hours=1)
        entries: list[_FakeEntry] = []
        for i in range(DEFAULT_THRESHOLD - 1):
            session_start = base + timedelta(hours=i)
            entries.append(_entry(query="alpha", when=session_start))
            entries.append(
                _entry(query="beta", when=session_start + timedelta(minutes=2)),
            )
        report = await detect_co_occurrence_patterns(_FakeLog(entries))
        assert report.suggestions == []

    @pytest.mark.asyncio
    async def test_signature_normalises_word_order(self) -> None:
        base = datetime.now() - timedelta(hours=1)
        entries: list[_FakeEntry] = []
        for i in range(DEFAULT_THRESHOLD):
            session_start = base + timedelta(hours=i)
            # "discount renewal" and "renewal discount" should collapse.
            entries.append(_entry(query="discount renewal", when=session_start))
            entries.append(
                _entry(query="renewal discount", when=session_start + timedelta(minutes=1)),
            )
        report = await detect_co_occurrence_patterns(_FakeLog(entries))
        # The pair counts as the same signature each time, but the two
        # queries normalise to the SAME token set so they don't form a
        # multi-query pair. Expect zero suggestions.
        assert report.suggestions == []


# ---------------------------------------------------------------------------
# Session boundary
# ---------------------------------------------------------------------------


class TestSessionBoundary:
    @pytest.mark.asyncio
    async def test_pair_separated_by_long_gap_not_grouped(self) -> None:
        # Same pair queries but separated by >15 minutes — NOT a session.
        base = datetime.now() - timedelta(days=1)
        entries: list[_FakeEntry] = []
        for i in range(DEFAULT_THRESHOLD * 2):
            entries.append(_entry(query="alpha", when=base + timedelta(minutes=60 * i)))
            entries.append(
                _entry(query="beta", when=base + timedelta(minutes=60 * i + 30)),
            )
        report = await detect_co_occurrence_patterns(_FakeLog(entries))
        assert report.suggestions == []


# ---------------------------------------------------------------------------
# Pocket + actor isolation
# ---------------------------------------------------------------------------


class TestIsolation:
    @pytest.mark.asyncio
    async def test_different_actors_do_not_co_occur_with_each_other(self) -> None:
        base = datetime.now() - timedelta(hours=1)
        entries: list[_FakeEntry] = []
        for i in range(DEFAULT_THRESHOLD):
            t = base + timedelta(hours=i)
            entries.append(_entry(actor="user:priya", query="alpha", when=t))
            entries.append(
                _entry(actor="user:maya", query="beta", when=t + timedelta(minutes=2)),
            )
        report = await detect_co_occurrence_patterns(_FakeLog(entries))
        assert report.suggestions == []

    @pytest.mark.asyncio
    async def test_pocket_filter_isolates(self) -> None:
        base = datetime.now() - timedelta(hours=1)
        entries: list[_FakeEntry] = []
        for i in range(DEFAULT_THRESHOLD):
            t = base + timedelta(hours=i)
            entries.append(_entry(pocket_id="p1", query="alpha", when=t))
            entries.append(
                _entry(pocket_id="p1", query="beta", when=t + timedelta(minutes=1)),
            )
            entries.append(_entry(pocket_id="p2", query="gamma", when=t))
            entries.append(
                _entry(pocket_id="p2", query="delta", when=t + timedelta(minutes=1)),
            )

        only_p1 = await detect_co_occurrence_patterns(_FakeLog(entries), pocket_id="p1")
        assert len(only_p1.suggestions) == 1
        assert only_p1.suggestions[0].pocket_id == "p1"


# ---------------------------------------------------------------------------
# Output shape
# ---------------------------------------------------------------------------


class TestOutputShape:
    @pytest.mark.asyncio
    async def test_report_includes_window_and_threshold(self) -> None:
        report = await detect_co_occurrence_patterns(
            _FakeLog([]),
            window_days=14,
            threshold=5,
        )
        assert report.window_days == 14
        assert report.threshold == 5
        assert report.scanned_traces == 0

    @pytest.mark.asyncio
    async def test_confidence_increases_with_count(self) -> None:
        base = datetime.now() - timedelta(hours=1)
        entries: list[_FakeEntry] = []
        for i in range(DEFAULT_THRESHOLD * 3):
            t = base + timedelta(hours=i)
            entries.append(_entry(query="alpha", when=t))
            entries.append(_entry(query="beta", when=t + timedelta(minutes=2)))
        report = await detect_co_occurrence_patterns(_FakeLog(entries))
        assert len(report.suggestions) == 1
        # 9 co-occurrences, threshold 3 → 9 / (3*3) = 1.0
        assert report.suggestions[0].confidence == pytest.approx(1.0, abs=0.01)
