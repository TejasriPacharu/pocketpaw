"""EEUploadService — workspace-scoped upload pipeline on top of the OSS service."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import UploadFile

from ee.cloud.uploads.mongo_store import MongoFileStore
from pocketpaw.uploads.adapter import StorageAdapter
from pocketpaw.uploads.config import UploadSettings
from pocketpaw.uploads.errors import NotFound
from pocketpaw.uploads.file_store import FileRecord
from pocketpaw.uploads.service import (
    BulkUploadResult,
    UploadService,
    _raise,
)


class _NullMeta:
    """Stub JSONLFileStore — validates but doesn't persist (EE uses Mongo)."""

    def save(self, record: FileRecord) -> None:
        pass

    def get(self, file_id: str) -> FileRecord | None:
        return None

    def soft_delete(self, file_id: str) -> None:
        pass


class EEUploadService:
    """Workspace-scoped upload pipeline.

    Wraps the OSS ``UploadService`` for validation + magic-byte sniff + adapter
    writes, then persists metadata to Mongo with workspace scoping.
    """

    def __init__(
        self,
        adapter: StorageAdapter,
        meta: MongoFileStore,
        cfg: UploadSettings,
    ) -> None:
        self._adapter = adapter
        self._meta = meta
        self._cfg = cfg
        # Use a null meta under OSS service so we control Mongo writes here
        self._oss = UploadService(adapter=adapter, meta=_NullMeta(), cfg=cfg)  # type: ignore[arg-type]

    async def upload(
        self, file: UploadFile, owner_id: str, chat_id: str | None, workspace: str,
    ) -> FileRecord:
        result = await self.upload_many([file], owner_id, chat_id, workspace)
        if result.failed:
            f = result.failed[0]
            _raise(f.code, f.reason)
        return result.uploaded[0]

    async def upload_many(
        self, files: list[UploadFile], owner_id: str, chat_id: str | None, workspace: str,
    ) -> BulkUploadResult:
        # Delegate validation + adapter writes; metadata is discarded inside OSS
        result = await self._oss.upload_many(files, owner_id, chat_id)
        # Persist each successful record in Mongo with workspace scoping
        for rec in result.uploaded:
            await self._meta.save_scoped(rec, workspace=workspace)
        return result

    async def stream(
        self, file_id: str, requester_id: str, workspace: str,
    ) -> tuple[FileRecord, AsyncIterator[bytes]]:
        rec = await self._meta.get_scoped(file_id, workspace=workspace)
        if rec is None:
            raise NotFound()
        if rec.owner_id != requester_id:
            # v1: owner-only. Chat-member check is a follow-up.
            raise NotFound()
        return rec, self._adapter.open(rec.storage_key)

    async def delete(
        self, file_id: str, requester_id: str, workspace: str,
    ) -> None:
        rec = await self._meta.get_scoped(file_id, workspace=workspace)
        if rec is None:
            raise NotFound()
        if rec.owner_id != requester_id:
            raise NotFound()
        await self._adapter.delete(rec.storage_key)
        await self._meta.soft_delete_scoped(file_id, workspace=workspace)
