# ee/retrieval/router.py — HTTP surface for the retrieval log.
# Created: 2026-04-13 (Move 4 PR-B) — GET /retrieval/log with filters,
# GET /retrieval/stats. Read-only — writes happen via the in-process sink.

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ee.retrieval.log import get_log
from ee.retrieval.models import RetrievalLogEntry

router = APIRouter(tags=["Retrieval"])


class RetrievalLogResponse(BaseModel):
    entries: list[RetrievalLogEntry]
    total: int


class RetrievalStatsResponse(BaseModel):
    total: int
    actors: int
    pockets: int


@router.get("/retrieval/log", response_model=RetrievalLogResponse)
async def list_retrieval_log(
    actor: str | None = Query(None, description="Filter by actor (e.g. 'user:sarah@co')"),
    source: str | None = Query(None, description="Filter by source (soul|kb|skill|fabric)"),
    pocket_id: str | None = Query(None, description="Filter by pocket"),
    since: datetime | None = Query(None, description="Only entries on/after this timestamp"),
    until: datetime | None = Query(None, description="Only entries on/before this timestamp"),
    limit: int = Query(100, ge=1, le=1000),
) -> RetrievalLogResponse:
    """Read the retrieval log with optional filters. Newest first."""
    entries = await get_log().read(
        actor=actor,
        source=source,
        pocket_id=pocket_id,
        since=since,
        until=until,
        limit=limit,
    )
    return RetrievalLogResponse(entries=entries, total=len(entries))


@router.get("/retrieval/stats", response_model=RetrievalStatsResponse)
async def retrieval_stats() -> RetrievalStatsResponse:
    """Summary counters across the full log."""
    stats = await get_log().stats()
    return RetrievalStatsResponse(**stats)
