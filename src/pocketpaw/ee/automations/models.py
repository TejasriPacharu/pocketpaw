# Automations models — Pydantic models for rule-based pocket automations.
# Created: 2026-03-30 — RuleType enum, Rule, CreateRuleRequest, UpdateRuleRequest.

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RuleType(str, Enum):
    THRESHOLD = "threshold"
    SCHEDULE = "schedule"
    DATA_CHANGE = "data_change"


class Rule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    pocket_id: str = ""
    name: str
    description: str = ""
    enabled: bool = True
    type: RuleType
    # Condition fields
    object_type: Optional[str] = None  # "Product", "Order", etc.
    property: Optional[str] = None  # "stock", "revenue", etc.
    operator: Optional[str] = None  # "less_than", "greater_than", "equals", "changed"
    value: Optional[str] = None
    schedule: Optional[str] = None  # cron expression or preset
    # Action
    action: str = ""  # what to do when rule fires
    # Stats
    last_fired: Optional[datetime] = None
    fire_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CreateRuleRequest(BaseModel):
    pocket_id: str = ""
    name: str
    description: str = ""
    type: RuleType
    object_type: Optional[str] = None
    property: Optional[str] = None
    operator: Optional[str] = None
    value: Optional[str] = None
    schedule: Optional[str] = None
    action: str = ""


class UpdateRuleRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    object_type: Optional[str] = None
    property: Optional[str] = None
    operator: Optional[str] = None
    value: Optional[str] = None
    schedule: Optional[str] = None
    action: Optional[str] = None
