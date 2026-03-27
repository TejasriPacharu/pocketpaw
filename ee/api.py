# Enterprise API — dependency injection for ee/ stores.
# Created: 2026-03-28 — Provides FabricStore + InstinctStore as FastAPI deps.

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ee.fabric.store import FabricStore
from ee.instinct.store import InstinctStore


def _db_path() -> Path:
    """Enterprise DB path — ~/.pocketpaw/enterprise.db"""
    p = Path.home() / ".pocketpaw"
    p.mkdir(parents=True, exist_ok=True)
    return p / "enterprise.db"


@lru_cache(maxsize=1)
def get_fabric_store() -> FabricStore:
    return FabricStore(_db_path())


@lru_cache(maxsize=1)
def get_instinct_store() -> InstinctStore:
    return InstinctStore(_db_path())
