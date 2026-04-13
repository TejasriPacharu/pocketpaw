# ee/retrieval/log.py — Async-safe JSONL sink + filtered reader.
# Created: 2026-04-13 (Move 4 PR-B) — Append-only file at
# ~/.pocketpaw/retrieval.jsonl. Reads stream the file with optional filters.
# Once line counts cross 10K-100K, swap the reader for an SQLite FTS index.

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

from ee.retrieval.models import RetrievalLogEntry

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path.home() / ".pocketpaw" / "retrieval.jsonl"


class RetrievalLog:
    """Async-safe JSONL sink for RetrievalTrace events.

    Single-process serialisation via an asyncio.Lock — protects against
    interleaved writes from concurrent recall callers in the same runtime.
    Cross-process safety is intentionally NOT provided here (run paw-runtime
    once per host); add file-locking later if multi-process emerges.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else DEFAULT_PATH
        self._lock = asyncio.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    async def append(
        self,
        trace: Any,
        *,
        session_id: str | None = None,
    ) -> RetrievalLogEntry:
        """Append a trace to the log. ``trace`` may be a Pydantic model or a dict."""
        trace_dict: dict[str, Any]
        if hasattr(trace, "model_dump"):
            trace_dict = trace.model_dump(mode="json")
        elif isinstance(trace, dict):
            trace_dict = trace
        else:
            raise TypeError(f"Unsupported trace type: {type(trace).__name__}")

        entry = RetrievalLogEntry(trace=trace_dict, session_id=session_id)
        line = entry.model_dump_json() + "\n"

        async with self._lock:
            await asyncio.to_thread(self._write, line)
        return entry

    def _write(self, line: str) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    async def read(
        self,
        *,
        actor: str | None = None,
        source: str | None = None,
        pocket_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> list[RetrievalLogEntry]:
        """Filtered read of the log. Returns newest-first up to ``limit`` rows."""
        rows: list[RetrievalLogEntry] = []
        if not self._path.exists():
            return rows
        async for entry in self._stream():
            if not _matches(entry, actor, source, pocket_id, since, until):
                continue
            rows.append(entry)
        rows.sort(key=lambda e: e.ingested_at, reverse=True)
        return rows[:limit]

    async def tail(self, n: int = 20) -> list[RetrievalLogEntry]:
        """Return the last ``n`` entries — newest last (terminal-friendly)."""
        rows = await self.read(limit=max(n, 1))
        rows.reverse()
        return rows

    async def stats(self) -> dict[str, int]:
        """Quick counters for ops dashboards."""
        if not self._path.exists():
            return {"total": 0, "actors": 0, "pockets": 0}
        actors: set[str] = set()
        pockets: set[str] = set()
        total = 0
        async for entry in self._stream():
            total += 1
            if entry.actor():
                actors.add(entry.actor())
            if entry.pocket_id():
                pockets.add(entry.pocket_id() or "")
        return {"total": total, "actors": len(actors), "pockets": len(pockets)}

    async def clear(self) -> None:
        """Truncate the log file. Used by tests; no production callers."""
        async with self._lock:
            if self._path.exists():
                await asyncio.to_thread(self._path.unlink)

    async def _stream(self) -> AsyncIterator[RetrievalLogEntry]:
        """Yield entries one at a time. Tolerant of malformed lines."""
        # Read in a worker thread to keep the event loop free.
        lines: list[str] = await asyncio.to_thread(self._read_lines)
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
                yield RetrievalLogEntry.model_validate(payload)
            except (ValueError, TypeError):
                logger.debug("Skipping malformed retrieval log line")
                continue

    def _read_lines(self) -> list[str]:
        with self._path.open("r", encoding="utf-8") as fh:
            return fh.readlines()


def _matches(
    entry: RetrievalLogEntry,
    actor: str | None,
    source: str | None,
    pocket_id: str | None,
    since: datetime | None,
    until: datetime | None,
) -> bool:
    if actor and entry.actor() != actor:
        return False
    if source and entry.source() != source:
        return False
    if pocket_id and entry.pocket_id() != pocket_id:
        return False
    if since and entry.ingested_at < since:
        return False
    if until and entry.ingested_at > until:
        return False
    return True


_singleton: RetrievalLog | None = None


def get_log() -> RetrievalLog:
    """Process-wide singleton sink. Override the path via POCKETPAW_RETRIEVAL_LOG."""
    global _singleton
    if _singleton is None:
        override = os.environ.get("POCKETPAW_RETRIEVAL_LOG")
        _singleton = RetrievalLog(path=override or None)
    return _singleton


def reset_log_for_tests() -> None:
    """Reset the singleton so tests can substitute paths cleanly."""
    global _singleton
    _singleton = None
