"""StorageAdapter protocol — the swap point for local, S3, etc."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    """Return value of ``StorageAdapter.put``."""

    key: str
    size: int
    mime: str


class StorageAdapter(Protocol):
    """Abstract byte storage. Knows nothing about metadata, auth, or mime logic.

    Implementations must be safe to call from asyncio contexts.
    """

    async def put(
        self, key: str, stream: AsyncIterator[bytes], mime: str
    ) -> StoredObject:
        """Persist ``stream`` at ``key``. Returns the canonical ``StoredObject``."""

    async def open(self, key: str) -> AsyncIterator[bytes]:  # pragma: no cover
        """Yield the stored bytes in chunks. Raises ``NotFound`` if missing."""

    async def delete(self, key: str) -> None:
        """Remove ``key`` if present. Idempotent."""

    async def exists(self, key: str) -> bool:
        """Return whether ``key`` is currently stored."""
