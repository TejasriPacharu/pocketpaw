# ee/widget_graduation/policy.py — Promotion + demotion thresholds for widgets.
# Created: 2026-04-13 (Move 8 PR-A) — Mirrors ee/graduation/policy. Reads the
# widget interaction log and emits WidgetDecision objects when usage crosses
# the configured thresholds.

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta

from ee.widget_graduation.log import WidgetInteractionLog
from ee.widget_graduation.models import WidgetDecision, WidgetReport

logger = logging.getLogger(__name__)


DEFAULT_WINDOW_DAYS = 30
DEFAULT_PIN_THRESHOLD = 10        # Interactions in window → pin
DEFAULT_FADE_THRESHOLD = 0        # Zero interactions in window → fade
DEFAULT_ARCHIVE_DAYS = 60         # Untouched longer than this → archive
_PROMOTING_ACTIONS = {"open", "edit", "click"}


async def scan_for_widget_decisions(
    log: WidgetInteractionLog,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    pin_threshold: int = DEFAULT_PIN_THRESHOLD,
    archive_days: int = DEFAULT_ARCHIVE_DAYS,
    pocket_id: str | None = None,
    actor: str | None = None,
) -> WidgetReport:
    """Scan the widget log and propose pin / fade / archive decisions.

    Pin: widget hit ``pin_threshold`` promoting interactions in the window.
    Fade: widget seen at least once historically but zero promoting
        interactions in the window.
    Archive: widget last touched more than ``archive_days`` ago.
    """
    since = datetime.now() - timedelta(days=window_days)
    long_ago = datetime.now() - timedelta(days=archive_days)

    promoting_in_window: Counter[tuple[str, str]] = Counter()
    last_seen: dict[tuple[str, str], datetime] = {}

    # Pull the long-window history so archive logic sees old entries too.
    archive_window_start = datetime.now() - timedelta(days=archive_days * 2)
    history = await log.read(
        pocket_id=pocket_id,
        actor=actor,
        since=archive_window_start,
        limit=100_000,
    )

    for entry in history:
        key = (entry.widget_id, entry.pocket_id)
        last_seen[key] = max(last_seen.get(key, entry.timestamp), entry.timestamp)
        if entry.action in _PROMOTING_ACTIONS and entry.timestamp >= since:
            promoting_in_window[key] += 1

    decisions: list[WidgetDecision] = []
    for key, count in promoting_in_window.items():
        if count >= pin_threshold:
            decisions.append(
                WidgetDecision(
                    widget_id=key[0],
                    pocket_id=key[1],
                    verdict="pin",
                    interactions_in_window=count,
                    window_days=window_days,
                    last_interaction=last_seen.get(key),
                    reason=(
                        f"Opened/edited/clicked {count}× in last {window_days} days "
                        f"(threshold {pin_threshold})."
                    ),
                ),
            )

    # Fade: widgets present in history but with no promoting interactions in window.
    for key, seen in last_seen.items():
        if key in promoting_in_window:
            continue
        if seen >= long_ago:
            decisions.append(
                WidgetDecision(
                    widget_id=key[0],
                    pocket_id=key[1],
                    verdict="fade",
                    interactions_in_window=0,
                    window_days=window_days,
                    last_interaction=seen,
                    reason="No promoting interactions in window.",
                ),
            )
        else:
            decisions.append(
                WidgetDecision(
                    widget_id=key[0],
                    pocket_id=key[1],
                    verdict="archive",
                    interactions_in_window=0,
                    window_days=window_days,
                    last_interaction=seen,
                    reason=f"Untouched for over {archive_days} days.",
                ),
            )

    return WidgetReport(
        decisions=decisions,
        scanned_interactions=len(history),
        window_days=window_days,
    )
