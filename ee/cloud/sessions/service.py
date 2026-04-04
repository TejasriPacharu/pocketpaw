"""Sessions domain — business logic service."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime

import httpx
from beanie import PydanticObjectId

from ee.cloud.models.session import Session
from ee.cloud.sessions.schemas import (
    CreateSessionRequest,
    SessionResponse,
    UpdateSessionRequest,
)
from ee.cloud.shared.errors import Forbidden, NotFound
from ee.cloud.shared.events import event_bus

logger = logging.getLogger(__name__)

RUNTIME_URL = os.environ.get("POCKETPAW_RUNTIME_URL", "http://localhost:8888")


def _session_response(session: Session) -> SessionResponse:
    """Build a SessionResponse from a Session document."""
    return SessionResponse(
        id=str(session.id),
        session_id=session.sessionId,
        workspace=session.workspace,
        owner=session.owner,
        title=session.title,
        pocket=session.pocket,
        group=session.group,
        agent=session.agent,
        message_count=session.messageCount,
        last_activity=session.lastActivity,
        created_at=session.createdAt,
        deleted_at=session.deleted_at,
    )


class SessionService:
    """Stateless service encapsulating session business logic."""

    # -----------------------------------------------------------------
    # CRUD
    # -----------------------------------------------------------------

    @staticmethod
    async def create(
        workspace_id: str, user_id: str, body: CreateSessionRequest
    ) -> SessionResponse:
        """Create a session. Optionally link to a pocket on creation."""
        session = Session(
            sessionId=str(uuid.uuid4()),
            workspace=workspace_id,
            owner=user_id,
            title=body.title,
            pocket=body.pocket_id,
            group=body.group_id,
            agent=body.agent_id,
        )
        await session.insert()

        await event_bus.emit(
            "session.created",
            {
                "session_id": str(session.id),
                "session_uuid": session.sessionId,
                "workspace_id": workspace_id,
                "owner_id": user_id,
                "pocket_id": body.pocket_id,
            },
        )

        return _session_response(session)

    @staticmethod
    async def list_sessions(
        workspace_id: str, user_id: str
    ) -> list[SessionResponse]:
        """List sessions for user in workspace, exclude deleted, sort by lastActivity desc."""
        sessions = (
            await Session.find(
                Session.workspace == workspace_id,
                Session.owner == user_id,
                Session.deleted_at == None,  # noqa: E711
            )
            .sort(-Session.lastActivity)
            .to_list()
        )
        return [_session_response(s) for s in sessions]

    @staticmethod
    async def get(session_id: str, user_id: str) -> SessionResponse:
        """Get a session by _id or sessionId. Verify owner."""
        session = await SessionService._get_session(session_id, user_id)
        return _session_response(session)

    @staticmethod
    async def update(
        session_id: str, user_id: str, body: UpdateSessionRequest
    ) -> SessionResponse:
        """Update session fields. Owner only."""
        session = await SessionService._get_session(session_id, user_id)

        if body.title is not None:
            session.title = body.title
        if body.pocket_id is not None:
            session.pocket = body.pocket_id

        await session.save()
        return _session_response(session)

    @staticmethod
    async def delete(session_id: str, user_id: str) -> None:
        """Soft-delete a session via deleted_at. Owner only."""
        session = await SessionService._get_session(session_id, user_id)
        session.deleted_at = datetime.now(UTC)
        await session.save()

    # -----------------------------------------------------------------
    # Pocket-scoped helpers
    # -----------------------------------------------------------------

    @staticmethod
    async def list_for_pocket(
        pocket_id: str, user_id: str
    ) -> list[SessionResponse]:
        """Find sessions where pocket == pocket_id."""
        sessions = (
            await Session.find(
                Session.pocket == pocket_id,
                Session.owner == user_id,
                Session.deleted_at == None,  # noqa: E711
            )
            .sort(-Session.lastActivity)
            .to_list()
        )
        return [_session_response(s) for s in sessions]

    @staticmethod
    async def create_for_pocket(
        workspace_id: str,
        user_id: str,
        pocket_id: str,
        body: CreateSessionRequest,
    ) -> SessionResponse:
        """Create a session with pocket already set."""
        body_with_pocket = CreateSessionRequest(
            title=body.title,
            pocket_id=pocket_id,
            group_id=body.group_id,
            agent_id=body.agent_id,
        )
        return await SessionService.create(workspace_id, user_id, body_with_pocket)

    # -----------------------------------------------------------------
    # Runtime proxy
    # -----------------------------------------------------------------

    @staticmethod
    async def get_history(session_id: str, user_id: str) -> dict:
        """Proxy to Python runtime: GET {RUNTIME_URL}/api/v1/sessions/{sessionId}/history."""
        session = await SessionService._get_session(session_id, user_id)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{RUNTIME_URL}/api/v1/sessions/{session.sessionId}/history",
                    timeout=10,
                )
                return resp.json()
        except Exception:
            logger.warning(
                "Failed to fetch history for session %s from runtime",
                session.sessionId,
            )
            return {"messages": [], "error": "Runtime unavailable"}

    # -----------------------------------------------------------------
    # Touch (activity tracking)
    # -----------------------------------------------------------------

    @staticmethod
    async def touch(session_id: str) -> None:
        """Update lastActivity and increment messageCount."""
        session = await Session.find_one(Session.sessionId == session_id)
        if session:
            session.lastActivity = datetime.now(UTC)
            session.messageCount += 1
            await session.save()

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    @staticmethod
    async def _get_session(session_id: str, user_id: str) -> Session:
        """Fetch by ObjectId first, then by sessionId. Verify owner."""
        session = None
        try:
            session = await Session.get(PydanticObjectId(session_id))
        except Exception:
            session = await Session.find_one(Session.sessionId == session_id)

        if not session or session.deleted_at:
            raise NotFound("session", session_id)
        if session.owner != user_id:
            raise Forbidden("session.not_owner", "Not the session owner")
        return session
