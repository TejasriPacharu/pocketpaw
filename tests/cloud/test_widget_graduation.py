# tests/cloud/test_widget_graduation.py — Move 8 PR-A.
# Created: 2026-04-13 — Append + read for the widget interaction log,
# pin/fade/archive verdict logic, threshold semantics, window boundaries.

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ee.widget_graduation.log import WidgetInteractionLog, reset_widget_log_for_tests
from ee.widget_graduation.models import WidgetInteraction
from ee.widget_graduation.policy import (
    DEFAULT_ARCHIVE_DAYS,
    DEFAULT_PIN_THRESHOLD,
    scan_for_widget_decisions,
)


def _interaction(
    widget_id: str = "w1",
    pocket_id: str = "pocket-1",
    actor: str = "user:priya",
    action: str = "open",
    timestamp: datetime | None = None,
) -> WidgetInteraction:
    return WidgetInteraction(
        widget_id=widget_id,
        pocket_id=pocket_id,
        actor=actor,
        action=action,  # type: ignore[arg-type]
        timestamp=timestamp or datetime.now(),
    )


@pytest.fixture(autouse=True)
def _reset():
    reset_widget_log_for_tests()
    yield
    reset_widget_log_for_tests()


@pytest.fixture
def log(tmp_path: Path) -> WidgetInteractionLog:
    return WidgetInteractionLog(path=tmp_path / "widget_test.jsonl")


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------


class TestLog:
    @pytest.mark.asyncio
    async def test_append_writes_jsonl_line(self, log: WidgetInteractionLog) -> None:
        await log.append(_interaction())
        rows = await log.read()
        assert len(rows) == 1
        assert rows[0].widget_id == "w1"

    @pytest.mark.asyncio
    async def test_filter_by_pocket(self, log: WidgetInteractionLog) -> None:
        await log.append(_interaction(pocket_id="p1"))
        await log.append(_interaction(pocket_id="p2"))
        rows = await log.read(pocket_id="p1")
        assert len(rows) == 1
        assert rows[0].pocket_id == "p1"

    @pytest.mark.asyncio
    async def test_filter_by_widget_id(self, log: WidgetInteractionLog) -> None:
        await log.append(_interaction(widget_id="w1"))
        await log.append(_interaction(widget_id="w2"))
        rows = await log.read(widget_id="w1")
        assert len(rows) == 1
        assert rows[0].widget_id == "w1"

    @pytest.mark.asyncio
    async def test_concurrent_append_preserves_lines(self, log: WidgetInteractionLog) -> None:
        await asyncio.gather(*(log.append(_interaction(actor=f"u{i}")) for i in range(15)))
        rows = await log.read()
        assert len(rows) == 15

    @pytest.mark.asyncio
    async def test_missing_file_returns_empty(self, log: WidgetInteractionLog) -> None:
        rows = await log.read()
        assert rows == []


# ---------------------------------------------------------------------------
# Policy: pin
# ---------------------------------------------------------------------------


class TestPin:
    @pytest.mark.asyncio
    async def test_widget_with_threshold_interactions_gets_pinned(
        self, log: WidgetInteractionLog
    ) -> None:
        for _ in range(DEFAULT_PIN_THRESHOLD):
            await log.append(_interaction(action="open"))
        report = await scan_for_widget_decisions(log)
        pinned = [d for d in report.decisions if d.verdict == "pin"]
        assert len(pinned) == 1
        assert pinned[0].widget_id == "w1"
        assert pinned[0].interactions_in_window == DEFAULT_PIN_THRESHOLD

    @pytest.mark.asyncio
    async def test_below_threshold_does_not_pin(self, log: WidgetInteractionLog) -> None:
        for _ in range(DEFAULT_PIN_THRESHOLD - 1):
            await log.append(_interaction(action="click"))
        report = await scan_for_widget_decisions(log)
        assert all(d.verdict != "pin" for d in report.decisions)

    @pytest.mark.asyncio
    async def test_only_promoting_actions_count(self, log: WidgetInteractionLog) -> None:
        # 'dismiss' and 'remove' are not promoting actions.
        for _ in range(DEFAULT_PIN_THRESHOLD):
            await log.append(_interaction(action="dismiss"))
        report = await scan_for_widget_decisions(log)
        assert all(d.verdict != "pin" for d in report.decisions)


# ---------------------------------------------------------------------------
# Policy: fade
# ---------------------------------------------------------------------------


class TestFade:
    @pytest.mark.asyncio
    async def test_recent_history_with_no_in_window_use_gets_faded(
        self, log: WidgetInteractionLog
    ) -> None:
        # Last seen ~10 days ago — within archive window, but no promoting
        # interactions in the 30-day pin window.
        ten_days_ago = datetime.now() - timedelta(days=40)
        await log.append(_interaction(action="open", timestamp=ten_days_ago))
        report = await scan_for_widget_decisions(log)
        faded = [d for d in report.decisions if d.verdict == "fade"]
        assert len(faded) == 1


# ---------------------------------------------------------------------------
# Policy: archive
# ---------------------------------------------------------------------------


class TestArchive:
    @pytest.mark.asyncio
    async def test_old_inactive_widget_archived(self, log: WidgetInteractionLog) -> None:
        old = datetime.now() - timedelta(days=DEFAULT_ARCHIVE_DAYS + 30)
        await log.append(_interaction(action="open", timestamp=old))
        report = await scan_for_widget_decisions(log)
        archived = [d for d in report.decisions if d.verdict == "archive"]
        assert len(archived) == 1
        assert "Untouched" in archived[0].reason


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


class TestFilters:
    @pytest.mark.asyncio
    async def test_pocket_filter_isolates_decisions(
        self, log: WidgetInteractionLog
    ) -> None:
        for _ in range(DEFAULT_PIN_THRESHOLD):
            await log.append(_interaction(action="open", pocket_id="p1"))
        for _ in range(DEFAULT_PIN_THRESHOLD):
            await log.append(_interaction(action="open", pocket_id="p2", widget_id="w2"))

        only_p1 = await scan_for_widget_decisions(log, pocket_id="p1")
        assert all(d.pocket_id == "p1" for d in only_p1.decisions)
        assert any(d.verdict == "pin" for d in only_p1.decisions)

    @pytest.mark.asyncio
    async def test_actor_filter_isolates_decisions(
        self, log: WidgetInteractionLog
    ) -> None:
        for _ in range(DEFAULT_PIN_THRESHOLD):
            await log.append(_interaction(action="open", actor="user:priya"))
        for _ in range(DEFAULT_PIN_THRESHOLD - 5):
            await log.append(
                _interaction(action="open", actor="user:maya", widget_id="w_maya"),
            )
        priya = await scan_for_widget_decisions(log, actor="user:priya")
        ids = {d.widget_id for d in priya.decisions if d.verdict == "pin"}
        assert ids == {"w1"}
