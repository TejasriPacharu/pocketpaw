"""Backend selection — ee flips memory_backend default to mongodb, OSS stays on file."""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import pytest


class TestCreateMemoryStoreMongoBranch:
    def test_mongodb_backend_returns_mongo_store(self):
        from ee.cloud.memory.mongo_store import MongoMemoryStore
        from pocketpaw.memory.manager import create_memory_store

        store = create_memory_store(backend="mongodb")
        assert isinstance(store, MongoMemoryStore)

    def test_file_backend_unchanged(self):
        from pocketpaw.memory.file_store import FileMemoryStore
        from pocketpaw.memory.manager import create_memory_store

        store = create_memory_store(backend="file")
        assert isinstance(store, FileMemoryStore)


class TestEeDefaultFlip:
    def test_flip_when_env_unset(self):
        from ee.cloud.memory.bootstrap import register_default_backend

        env = dict(os.environ)
        env.pop("POCKETPAW_MEMORY_BACKEND", None)
        with patch.dict(os.environ, env, clear=True):
            register_default_backend()
            assert os.environ["POCKETPAW_MEMORY_BACKEND"] == "mongodb"

    def test_preserves_explicit_file_choice(self):
        from ee.cloud.memory.bootstrap import register_default_backend

        env = dict(os.environ)
        env["POCKETPAW_MEMORY_BACKEND"] = "file"
        with patch.dict(os.environ, env, clear=True):
            register_default_backend()
            assert os.environ["POCKETPAW_MEMORY_BACKEND"] == "file"

    def test_preserves_explicit_mem0_choice(self):
        from ee.cloud.memory.bootstrap import register_default_backend

        env = dict(os.environ)
        env["POCKETPAW_MEMORY_BACKEND"] = "mem0"
        with patch.dict(os.environ, env, clear=True):
            register_default_backend()
            assert os.environ["POCKETPAW_MEMORY_BACKEND"] == "mem0"

    def test_primes_manager_singleton_with_mongo_store(self):
        """After flip, get_memory_manager()._store is a MongoMemoryStore.

        Bypasses ``Settings.load()`` since that reads ``~/.pocketpaw/config.json``
        which may carry a stale ``memory_backend`` value from earlier sessions.
        """
        from ee.cloud.memory.bootstrap import register_default_backend
        from ee.cloud.memory.mongo_store import MongoMemoryStore
        from pocketpaw.memory.manager import get_memory_manager

        env = dict(os.environ)
        env.pop("POCKETPAW_MEMORY_BACKEND", None)
        with patch.dict(os.environ, env, clear=True):
            register_default_backend()
            manager = get_memory_manager()
            assert isinstance(manager._store, MongoMemoryStore)


class TestOssIsolation:
    def test_no_top_level_ee_imports_in_pocketpaw_memory(self):
        """``src/pocketpaw/memory`` must not import from ``ee.*`` at module top."""
        import pathlib

        mem_dir = pathlib.Path("src/pocketpaw/memory")
        assert mem_dir.is_dir(), f"{mem_dir} not found"

        for py in mem_dir.rglob("*.py"):
            src = py.read_text(encoding="utf-8")
            # Strip function bodies crudely by looking only at module-level lines.
            for line in src.splitlines():
                stripped = line.lstrip()
                indent = len(line) - len(stripped)
                if indent == 0 and (
                    stripped.startswith("from ee.") or stripped.startswith("import ee.")
                ):
                    raise AssertionError(f"top-level ee import in {py}: {stripped}")

    def test_create_memory_store_import_chain_does_not_pull_ee(self):
        """Importing ``pocketpaw.memory.manager`` must not import ``ee.*``."""
        # Force a clean import by dropping any primed modules.
        for mod in list(__import__("sys").modules):
            if mod.startswith("pocketpaw.memory.manager") or mod.startswith("ee.cloud.memory"):
                __import__("sys").modules.pop(mod, None)

        importlib.import_module("pocketpaw.memory.manager")
        # The ee.cloud.memory package should NOT have been loaded as a side effect.
        assert "ee.cloud.memory.mongo_store" not in __import__("sys").modules, (
            "pocketpaw.memory.manager should not eager-import the ee mongo store"
        )


# Note: we intentionally don't run ``init_cloud_db`` in a unit test here.
# Re-initialising Beanie mid-suite leaves cached document metadata that
# breaks subsequent tests. ``test_flip_when_env_unset`` +
# ``test_primes_manager_singleton_with_mongo_store`` cover the same contract
# without touching the global Beanie registry. The smoke test at
# ``scripts/smoke_mongo_memory.py`` exercises the full ``init_cloud_db`` path
# end-to-end in isolation.


@pytest.fixture(autouse=True)
def _reset_memory_manager_singleton():
    """Reset the global manager cache between tests in this module."""
    yield
    try:
        import pocketpaw.memory.manager as _mm

        _mm._manager = None
    except Exception:
        pass
    try:
        from pocketpaw.config import get_settings

        get_settings.cache_clear()
    except Exception:
        pass
