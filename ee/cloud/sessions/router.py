"""Sessions domain — FastAPI router."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from starlette.responses import Response

from ee.cloud.license import require_license
from ee.cloud.sessions.schemas import (
    CreateSessionRequest,
    UpdateSessionRequest,
)
from ee.cloud.sessions.service import SessionService
from ee.cloud.shared.deps import current_user_id, current_workspace_id

router = APIRouter(
    prefix="/sessions", tags=["Sessions"], dependencies=[Depends(require_license)]
)

# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("")
async def create_session(
    body: CreateSessionRequest,
    workspace_id: str = Depends(current_workspace_id),
    user_id: str = Depends(current_user_id),
) -> dict:
    return await SessionService.create(workspace_id, user_id, body)


@router.get("")
async def list_sessions(
    workspace_id: str = Depends(current_workspace_id),
    user_id: str = Depends(current_user_id),
) -> list[dict]:
    return await SessionService.list_sessions(workspace_id, user_id)


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    user_id: str = Depends(current_user_id),
) -> dict:
    return await SessionService.get(session_id, user_id)


@router.patch("/{session_id}")
async def update_session(
    session_id: str,
    body: UpdateSessionRequest,
    user_id: str = Depends(current_user_id),
) -> dict:
    return await SessionService.update(session_id, user_id, body)


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    user_id: str = Depends(current_user_id),
) -> Response:
    await SessionService.delete(session_id, user_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# History proxy & activity tracking
# ---------------------------------------------------------------------------


@router.get("/{session_id}/history")
async def get_session_history(
    session_id: str,
    user_id: str = Depends(current_user_id),
) -> dict:
    return await SessionService.get_history(session_id, user_id)


@router.post("/{session_id}/touch", status_code=204)
async def touch_session(session_id: str) -> Response:
    await SessionService.touch(session_id)
    return Response(status_code=204)
