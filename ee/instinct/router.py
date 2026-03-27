# Instinct API router — REST endpoints for the decision pipeline.
# Created: 2026-03-28 — Action lifecycle, approvals, audit log.

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ee.api import get_instinct_store
from ee.instinct.models import ActionCategory, ActionPriority, ActionTrigger, ActionContext
from ee.instinct.store import InstinctStore

router = APIRouter(prefix="/api/v1/instinct", tags=["instinct"])


# --- Request Models ---

class ProposeActionRequest(BaseModel):
    pocket_id: str
    title: str
    description: str = ""
    category: str = "workflow"
    priority: str = "medium"
    recommendation: str
    parameters: dict[str, Any] = {}
    trigger: ActionTrigger
    context: ActionContext | None = None


class ApproveRequest(BaseModel):
    approver: str = "user"


class RejectRequest(BaseModel):
    reason: str = ""
    rejector: str = "user"


class ExecuteRequest(BaseModel):
    outcome: str | None = None


# --- Actions ---

@router.get("/actions")
async def list_actions(
    pocket_id: str | None = None,
    status: str | None = None,
    store: InstinctStore = Depends(get_instinct_store),
):
    if pocket_id:
        actions = await store.for_pocket(pocket_id)
    elif status:
        from ee.instinct.models import ActionStatus
        actions = await store._query_actions(status=ActionStatus(status))
    else:
        actions = await store._query_actions()
    return [a.model_dump(mode="json") for a in actions]


@router.post("/actions", status_code=201)
async def propose_action(req: ProposeActionRequest, store: InstinctStore = Depends(get_instinct_store)):
    action = await store.propose(
        pocket_id=req.pocket_id, title=req.title, description=req.description,
        recommendation=req.recommendation, trigger=req.trigger,
        category=ActionCategory(req.category),
        priority=ActionPriority(req.priority),
        parameters=req.parameters, context=req.context,
    )
    return action.model_dump(mode="json")


@router.get("/actions/{action_id}")
async def get_action(action_id: str, store: InstinctStore = Depends(get_instinct_store)):
    action = await store.get_action(action_id)
    if not action:
        raise HTTPException(404, "Action not found")
    return action.model_dump(mode="json")


@router.post("/actions/{action_id}/approve")
async def approve_action(action_id: str, req: ApproveRequest, store: InstinctStore = Depends(get_instinct_store)):
    action = await store.approve(action_id, req.approver)
    if not action:
        raise HTTPException(404, "Action not found")
    return action.model_dump(mode="json")


@router.post("/actions/{action_id}/reject")
async def reject_action(action_id: str, req: RejectRequest, store: InstinctStore = Depends(get_instinct_store)):
    action = await store.reject(action_id, req.reason, req.rejector)
    if not action:
        raise HTTPException(404, "Action not found")
    return action.model_dump(mode="json")


@router.post("/actions/{action_id}/execute")
async def execute_action(action_id: str, req: ExecuteRequest, store: InstinctStore = Depends(get_instinct_store)):
    action = await store.mark_executed(action_id, req.outcome)
    if not action:
        raise HTTPException(404, "Action not found")
    return action.model_dump(mode="json")


# --- Pending Queue ---

@router.get("/pending")
async def get_pending(
    pocket_id: str | None = None,
    store: InstinctStore = Depends(get_instinct_store),
):
    actions = await store.pending(pocket_id)
    return [a.model_dump(mode="json") for a in actions]


@router.get("/pending/count")
async def get_pending_count(
    pocket_id: str | None = None,
    store: InstinctStore = Depends(get_instinct_store),
):
    count = await store.pending_count(pocket_id)
    return {"count": count}


# --- Audit Log ---

@router.get("/audit")
async def query_audit(
    pocket_id: str | None = None,
    category: str | None = None,
    event: str | None = None,
    limit: int = Query(100, le=1000),
    store: InstinctStore = Depends(get_instinct_store),
):
    entries = await store.query_audit(
        pocket_id=pocket_id, category=category, event=event, limit=limit,
    )
    return [e.model_dump(mode="json") for e in entries]


@router.get("/audit/export")
async def export_audit(
    pocket_id: str | None = None,
    store: InstinctStore = Depends(get_instinct_store),
):
    from fastapi.responses import JSONResponse
    data = await store.export_audit(pocket_id)
    return JSONResponse(content={"entries": __import__("json").loads(data)})
