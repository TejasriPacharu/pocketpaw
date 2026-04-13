# ee/widget_graduation/log.py — Append-only JSONL widget interaction log.
# Created: 2026-04-13 (Move 8 PR-A) — Same JSONL pattern as ee/retrieval/log,
# scoped to widget events. Lives at ~/.pocketpaw/widget-interactions.jsonl
# (override via POCKETPAW_WIDGET_LOG). Read by the graduation policy.

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

from ee.widget_graduation.models import WidgetInteraction

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path.home() / ".pocketpaw" / "widget-interactions.jsonl"


class WidgetInteractionLog:
    """Async-safe append + streaming read for widget interactions."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else DEFAULT_PATH
        self._lock = asyncio.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    async def append(self, interaction: WidgetInteraction) -> WidgetInteraction:
        line = interaction.model_dump_json() + "\n"
        async with self._lock:
            await asyncio.to_thread(self._write, line)
        return interaction

    def _write(self, line: str) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    async def read(
        self,
        *,
        widget_id: str | None = None,
        pocket_id: str | None = None,
        actor: str | None = None,
        since: datetime | None = None,
        limit: int = 1000,
    ) -> list[WidgetInteraction]:
        if not self._path.exists():
            return []
        rows: list[WidgetInteraction] = []
        async for entry in self._stream():
            if widget_id and entry.widget_id != widget_id:
                continue
            if pocket_id and entry.pocket_id != pocket_id:
                continue
            if actor and entry.actor != actor:
                continue
            if since and entry.timestamp < since:
                continue
            rows.append(entry)
        rows.sort(key=lambda r: r.timestamp, reverse=True)
        return rows[:limit]

    async def clear(self) -> None:
        async with self._lock:
            if self._path.exists():
                await asyncio.to_thread(self._path.unlink)

    async def _stream(self) -> AsyncIterator[WidgetInteraction]:
        lines: list[str] = await asyncio.to_thread(self._read_lines)
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield WidgetInteraction.model_validate_json(raw)
            except (ValueError, TypeError):
                logger.debug("Skipping malformed widget log line")
                continue

    def _read_lines(self) -> list[str]:
        with self._path.open("r", encoding="utf-8") as fh:
            return fh.readlines()


_singleton: WidgetInteractionLog | None = None


def get_widget_log() -> WidgetInteractionLog:
    """Process-wide singleton. Override path via POCKETPAW_WIDGET_LOG."""
    global _singleton
    if _singleton is None:
        override = os.environ.get("POCKETPAW_WIDGET_LOG")
        _singleton = WidgetInteractionLog(path=override or None)
    return _singleton


def reset_widget_log_for_tests() -> None:
    global _singleton
    _singleton = None
