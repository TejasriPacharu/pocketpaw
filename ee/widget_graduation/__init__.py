# Widget Graduation — same primitive as memory graduation, applied to widgets.
# Created: 2026-04-13 (Move 8 PR-A) — Widgets a user opens often get pinned;
# widgets ignored for a window get archived. Reads from the widget interaction
# log and emits WidgetDecision objects (analogous to GraduationDecision in
# ee/graduation). The captain's "intelligent UI" thesis materialises here:
# the same memory-tier promotion mechanism, applied to UI elements.

from ee.widget_graduation.log import WidgetInteractionLog, get_widget_log
from ee.widget_graduation.models import (
    WidgetDecision,
    WidgetInteraction,
    WidgetReport,
)
from ee.widget_graduation.policy import scan_for_widget_decisions

__all__ = [
    "WidgetDecision",
    "WidgetInteraction",
    "WidgetInteractionLog",
    "WidgetReport",
    "get_widget_log",
    "scan_for_widget_decisions",
]
