# Widget Suggestions — agent reads retrieval patterns and proposes new widgets.
# Created: 2026-04-13 (Move 8 PR-B) — Companion to widget graduation: graduation
# moves existing widgets up/down based on use, suggestions create NEW widgets
# from observed retrieval co-occurrence ("user asks about X then Y three times
# in a row → propose a widget that surfaces both side-by-side").

from ee.widget_suggestions.detector import detect_co_occurrence_patterns
from ee.widget_suggestions.models import (
    PatternMatch,
    SuggestedWidget,
    SuggestionReport,
)

__all__ = [
    "PatternMatch",
    "SuggestedWidget",
    "SuggestionReport",
    "detect_co_occurrence_patterns",
]
