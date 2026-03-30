# Automations router — REST API for rule-based pocket automations.
# Created: 2026-03-30 — CRUD endpoints, toggle, mounted at /api/v1/automations.

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from pocketpaw.ee.automations.models import CreateRuleRequest, Rule, UpdateRuleRequest
from pocketpaw.ee.automations.store import get_automation_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automations", tags=["Automations"])


@router.get("/rules", response_model=list[Rule])
async def list_rules(pocket_id: Optional[str] = None):
    """List all automation rules, optionally filtered by pocket_id."""
    store = get_automation_store()
    return store.list_rules(pocket_id=pocket_id)


@router.post("/rules", response_model=Rule, status_code=201)
async def create_rule(body: CreateRuleRequest):
    """Create a new automation rule."""
    store = get_automation_store()
    return store.create_rule(body)


@router.get("/rules/{rule_id}", response_model=Rule)
async def get_rule(rule_id: str):
    """Get a single automation rule by ID."""
    store = get_automation_store()
    rule = store.get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    return rule


@router.patch("/rules/{rule_id}", response_model=Rule)
async def update_rule(rule_id: str, body: UpdateRuleRequest):
    """Update an existing automation rule (partial update)."""
    store = get_automation_store()
    try:
        return store.update_rule(rule_id, body)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """Delete an automation rule."""
    store = get_automation_store()
    deleted = store.delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    return {"ok": True, "id": rule_id}


@router.post("/rules/{rule_id}/toggle", response_model=Rule)
async def toggle_rule(rule_id: str):
    """Toggle the enabled state of an automation rule."""
    store = get_automation_store()
    try:
        return store.toggle_rule(rule_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
