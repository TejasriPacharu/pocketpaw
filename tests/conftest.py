"""Pytest configuration."""

import asyncio
import sys
from unittest.mock import patch

import pytest

from pocketpaw.security.audit import AuditLogger


@pytest.fixture(scope="session", autouse=True)
def _setup_asyncio_child_watcher():
    """Attach a child watcher so subprocess-based tests don't crash.

    On Python < 3.12 the default child watcher requires attachment to
    the running event loop.  On 3.12+ child watchers were removed, so
    this is a no-op.
    """
    if sys.version_info < (3, 12) and hasattr(asyncio, "ThreadedChildWatcher"):
        watcher = asyncio.ThreadedChildWatcher()
        asyncio.set_child_watcher(watcher)
    yield


@pytest.fixture(autouse=True)
def _isolate_audit_log(tmp_path):
    """Prevent tests from writing to the real ~/.pocketpaw/audit.jsonl.

    Creates a temp audit logger per test and patches the singleton so
    ToolRegistry.execute() and any other callers write to a throwaway file.
    """
    temp_logger = AuditLogger(log_path=tmp_path / "audit.jsonl")
    with (
        patch("pocketpaw.security.audit._audit_logger", temp_logger),
        patch("pocketpaw.security.audit.get_audit_logger", return_value=temp_logger),
        patch("pocketpaw.tools.registry.get_audit_logger", return_value=temp_logger),
    ):
        yield temp_logger
