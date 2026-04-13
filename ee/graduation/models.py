# ee/graduation/models.py — GraduationDecision + report types.
# Created: 2026-04-13 — Decisions describe the change without making it.
# Apply mode reads decisions and mutates the soul; dry-run (default) just
# emits them so an operator can review before promoting.

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

GraduationKind = Literal["episodic_to_semantic", "semantic_to_core", "promote_procedural"]


class GraduationDecision(BaseModel):
    """One memory crossed an access threshold — propose a tier change."""

    memory_id: str
    actor: str = ""
    pocket_id: str | None = None
    kind: GraduationKind
    access_count: int
    window_days: int
    from_tier: str | None = None
    to_tier: str
    reason: str = ""

    def short(self) -> str:
        """One-line summary for terminal output."""
        from_label = self.from_tier or "?"
        return (
            f"[{self.kind}] {self.memory_id} {from_label}→{self.to_tier} "
            f"({self.access_count} accesses in {self.window_days}d)"
        )


class GraduationReport(BaseModel):
    """The output of one scan."""

    decisions: list[GraduationDecision] = Field(default_factory=list)
    scanned_entries: int = 0
    window_days: int = 30
    dry_run: bool = True
    generated_at: datetime = Field(default_factory=datetime.now)
