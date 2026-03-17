# A2A Protocol — Pydantic models for request/response payloads.
#
# Follows the A2A Protocol specification:
# https://google.github.io/A2A/specification/
#
# Task lifecycle: submitted → working → completed | failed | canceled
# Supports text and tool-call content parts.

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class TaskState(enum.StrEnum):
    """A2A task lifecycle states."""

    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    INPUT_REQUIRED = "input_required"


class TextPart(BaseModel):
    """A plain-text content part."""

    type: str = "text"
    text: str


class A2AMessage(BaseModel):
    """A single message in an A2A task conversation."""

    role: str  # "user" | "agent"
    parts: list[TextPart]


class TaskStatus(BaseModel):
    """Current status of a task."""

    state: TaskState
    message: A2AMessage | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class Task(BaseModel):
    """An A2A task resource."""

    id: str
    session_id: str | None = None
    status: TaskStatus
    history: list[A2AMessage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskSendParams(BaseModel):
    """Parameters for tasks/send."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    session_id: str | None = None
    message: A2AMessage
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentCapabilities(BaseModel):
    """Agent capability flags advertised in the agent card."""

    streaming: bool = True
    push_notifications: bool = False
    state_transition_history: bool = True


class AgentCard(BaseModel):
    """A2A Agent Card — advertised at /.well-known/agent.json."""

    name: str
    description: str
    url: str
    version: str
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    skills: list[dict[str, Any]] = Field(default_factory=list)
    default_input_modes: list[str] = Field(default=["text"])
    default_output_modes: list[str] = Field(default=["text"])
