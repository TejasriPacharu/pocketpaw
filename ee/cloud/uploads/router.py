"""EE /uploads router — workspace-scoped upload endpoints."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from ee.cloud.license import require_license
from ee.cloud.shared.deps import current_user_id, current_workspace_id
from ee.cloud.uploads.mongo_store import MongoFileStore
from ee.cloud.uploads.service import EEUploadService
from pocketpaw.uploads.config import INLINE_MIMES, UploadSettings
from pocketpaw.uploads.errors import NotFound
from pocketpaw.uploads.local import LocalStorageAdapter

# Module-level singletons — one adapter + store per process
_ROOT = Path.home() / ".pocketpaw" / "uploads"
_CFG = UploadSettings(local_root=_ROOT)
_ADAPTER = LocalStorageAdapter(root=_ROOT)
_META = MongoFileStore()
_SVC = EEUploadService(adapter=_ADAPTER, meta=_META, cfg=_CFG)

router = APIRouter(
    prefix="/uploads",
    tags=["Uploads"],
    dependencies=[Depends(require_license)],
)


def _record_to_dict(rec) -> dict:
    return {
        "id": rec.id,
        "filename": rec.filename,
        "mime": rec.mime,
        "size": rec.size,
        "url": f"/api/v1/uploads/{rec.id}",
        "created": rec.created.isoformat(),
    }


@router.post("")
async def upload(
    files: Annotated[list[UploadFile], File(...)],
    chat_id: Annotated[str | None, Form()] = None,
    workspace: str = Depends(current_workspace_id),
    user_id: str = Depends(current_user_id),
) -> dict:
    try:
        result = await _SVC.upload_many(files, user_id, chat_id, workspace)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "uploaded": [_record_to_dict(r) for r in result.uploaded],
        "failed": [asdict(f) for f in result.failed],
    }


@router.get("/{file_id}")
async def download(
    file_id: str,
    workspace: str = Depends(current_workspace_id),
    user_id: str = Depends(current_user_id),
) -> StreamingResponse:
    try:
        rec, it = await _SVC.stream(file_id, user_id, workspace)
    except NotFound as e:
        raise HTTPException(status_code=404, detail="not found") from e
    disposition = "inline" if rec.mime in INLINE_MIMES else "attachment"
    return StreamingResponse(
        it,
        media_type=rec.mime,
        headers={"Content-Disposition": f'{disposition}; filename="{rec.filename}"'},
    )


@router.delete("/{file_id}", status_code=204)
async def delete_upload(
    file_id: str,
    workspace: str = Depends(current_workspace_id),
    user_id: str = Depends(current_user_id),
) -> Response:
    try:
        await _SVC.delete(file_id, user_id, workspace)
    except NotFound as e:
        raise HTTPException(status_code=404, detail="not found") from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
