"""Mongo-backed metadata store, workspace-scoped."""

from __future__ import annotations

from datetime import UTC, datetime

from ee.cloud.uploads.models import FileUpload
from pocketpaw.uploads.file_store import FileRecord


class MongoFileStore:
    """Workspace-scoped metadata store for EE uploads."""

    async def save_scoped(self, record: FileRecord, workspace: str) -> None:
        doc = FileUpload(
            file_id=record.id,
            storage_key=record.storage_key,
            filename=record.filename,
            mime=record.mime,
            size=record.size,
            workspace=workspace,
            owner=record.owner_id,
            chat_id=record.chat_id,
        )
        await doc.insert()

    async def get_scoped(self, file_id: str, workspace: str) -> FileRecord | None:
        doc = await FileUpload.find_one(
            FileUpload.file_id == file_id,
            FileUpload.workspace == workspace,
            FileUpload.deleted_at == None,  # noqa: E711 beanie needs literal None
        )
        if doc is None:
            return None
        return FileRecord(
            id=doc.file_id,
            storage_key=doc.storage_key,
            filename=doc.filename,
            mime=doc.mime,
            size=doc.size,
            owner_id=doc.owner,
            chat_id=doc.chat_id,
            created=doc.createdAt or datetime.now(UTC),
        )

    async def soft_delete_scoped(self, file_id: str, workspace: str) -> None:
        doc = await FileUpload.find_one(
            FileUpload.file_id == file_id,
            FileUpload.workspace == workspace,
        )
        if doc is None:
            return
        doc.deleted_at = datetime.now(UTC)
        await doc.save()
