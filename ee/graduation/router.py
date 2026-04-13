# ee/graduation/router.py — HTTP surface for the graduation policy.
# Created: 2026-04-13 (Move 4 PR-C) — Scan endpoint returns proposed
# decisions; apply endpoint mutates the soul (opt-in via body flag).

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ee.graduation.models import GraduationDecision, GraduationReport
from ee.graduation.policy import (
    DEFAULT_EPISODIC_THRESHOLD,
    DEFAULT_SEMANTIC_THRESHOLD,
    DEFAULT_WINDOW_DAYS,
    apply_decisions,
    scan_for_graduations,
)
from ee.retrieval.log import get_log

router = APIRouter(tags=["Graduation"])


class ScanRequest(BaseModel):
    window_days: int = DEFAULT_WINDOW_DAYS
    episodic_threshold: int = DEFAULT_EPISODIC_THRESHOLD
    semantic_threshold: int = DEFAULT_SEMANTIC_THRESHOLD
    actor: str | None = None
    pocket_id: str | None = None


class ApplyRequest(BaseModel):
    decisions: list[GraduationDecision] = Field(default_factory=list)


class ApplyResponse(BaseModel):
    applied: list[GraduationDecision]
    skipped: int


@router.post("/graduation/scan", response_model=GraduationReport)
async def scan_graduations(
    req: ScanRequest | None = None,
    dry_run: int = Query(1, description="Pass 0 to NOT prefix the report as dry-run"),
) -> GraduationReport:
    """Scan the retrieval log for memories that crossed access thresholds."""
    req = req or ScanRequest()
    return await scan_for_graduations(
        get_log(),
        window_days=req.window_days,
        episodic_threshold=req.episodic_threshold,
        semantic_threshold=req.semantic_threshold,
        actor=req.actor,
        pocket_id=req.pocket_id,
        dry_run=bool(dry_run),
    )


@router.post("/graduation/apply", response_model=ApplyResponse)
async def apply_graduations(req: ApplyRequest) -> ApplyResponse:
    """Apply the supplied decisions against the active soul.

    Returns the subset that succeeded. Failures are logged server-side and
    counted in ``skipped`` so the caller can retry only the failed entries.
    """
    try:
        from pocketpaw.soul.manager import get_soul_manager
    except ImportError as exc:
        raise HTTPException(503, f"Soul manager unavailable: {exc}") from exc

    manager = get_soul_manager()
    soul = getattr(manager, "soul", None) if manager else None
    if soul is None:
        raise HTTPException(503, "No soul loaded — cannot apply graduations")

    applied = await apply_decisions(soul, req.decisions)
    return ApplyResponse(applied=applied, skipped=len(req.decisions) - len(applied))
