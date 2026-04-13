# ee/widget_graduation/models.py — Widget interaction + graduation models.
# Created: 2026-04-13 (Move 8 PR-A) — Mirrors the shape of ee/graduation
# but keyed on widget IDs instead of memory IDs. The same scan + threshold
# pattern applies; the UI consumes WidgetDecision to pin / fade widgets.

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

WidgetAction = Literal["open", "edit", "click", "dismiss", "remove"]
WidgetVerdict = Literal["pin", "fade", "archive"]


class WidgetInteraction(BaseModel):
    """One user interaction with a widget. Append-only log entry."""

    widget_id: str
    pocket_id: str
    actor: str
    action: WidgetAction
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict)


class WidgetDecision(BaseModel):
    """A proposed UI mutation produced by the graduation policy.

    The UI applies it (or shows it as a suggestion in the chat panel
    depending on operator preference). Decisions are advisory — never
    write directly to the pocket spec without going through the
    existing widget mutation flow.
    """

    widget_id: str
    pocket_id: str
    verdict: WidgetVerdict
    interactions_in_window: int
    window_days: int
    reason: str = ""
    last_interaction: datetime | None = None


class WidgetReport(BaseModel):
    """Output of one graduation scan."""

    decisions: list[WidgetDecision] = Field(default_factory=list)
    scanned_interactions: int = 0
    window_days: int = 30
    generated_at: datetime = Field(default_factory=datetime.now)
