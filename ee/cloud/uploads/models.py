"""EE FileUpload document — Mongo metadata for blobs stored via StorageAdapter."""

from __future__ import annotations

from datetime import datetime

from beanie import Indexed

from ee.cloud.models.base import TimestampedDocument


class FileUpload(TimestampedDocument):
    """Metadata for one uploaded file. Blob bytes live in the StorageAdapter.

    Distinct from ``ee.cloud.models.file.FileObj`` (pre-signed URL storage):
    ``FileUpload`` is the adapter-backed path for chat attachments, with
    workspace scoping and soft-delete.
    """

    file_id: Indexed(str, unique=True)  # type: ignore[valid-type]
    storage_key: str
    filename: str
    mime: str
    size: int
    workspace: Indexed(str)  # type: ignore[valid-type]
    owner: str
    chat_id: Indexed(str) | None = None  # type: ignore[valid-type]
    deleted_at: datetime | None = None

    class Settings:
        name = "file_uploads"
        indexes = [
            [("workspace", 1), ("chat_id", 1), ("createdAt", -1)],
            [("workspace", 1), ("owner", 1), ("createdAt", -1)],
        ]
