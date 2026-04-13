# ee/widget_suggestions/models.py — Suggestion + co-occurrence types.
# Created: 2026-04-13 (Move 8 PR-B) — A SuggestedWidget is a proposal the
# agent surfaces in chat. The user accepts and the runtime pushes a widget
# spec into the pocket. PatternMatch is the raw signal (a co-occurring
# query pair detected in the retrieval log).

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PatternMatch(BaseModel):
    """One co-occurring query pattern detected in the retrieval log.

    ``signature`` is the joined sorted query terms so duplicate
    co-occurrences collapse into a single match. ``count`` is how many
    times the pattern repeated within the window. ``recent_actors`` lets
    the UI personalise the suggestion.
    """

    signature: str
    queries: list[str]
    count: int
    pocket_id: str | None = None
    recent_actors: list[str] = Field(default_factory=list)


class SuggestedWidget(BaseModel):
    """A proposal the agent shows the user inside pocket chat."""

    id: str
    pocket_id: str | None = None
    title: str
    description: str
    widget_type: str = "list"  # list | chart | kpi | chat
    pattern: PatternMatch
    confidence: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)


class SuggestionReport(BaseModel):
    """Output of one detection pass."""

    suggestions: list[SuggestedWidget] = Field(default_factory=list)
    scanned_traces: int = 0
    window_days: int = 7
    threshold: int = 3
    generated_at: datetime = Field(default_factory=datetime.now)
