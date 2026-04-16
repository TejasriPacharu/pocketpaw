"""Pytest configuration."""

from unittest.mock import patch

import pytest

from pocketpaw.security.audit import AuditLogger


@pytest.fixture(autouse=True)
def _enable_test_full_access(request, monkeypatch):
    """Flip the require_scope testing-bypass on for all tests by default.

    Router-only tests (which mount FastAPI routers without the dashboard
    middleware) can't set request.state.full_access on their own — this
    fixture lets them exercise route logic without every fixture having
    to install middleware. Tests that explicitly verify fail-closed
    scope behaviour use the ``enforce_scope`` marker to opt out.
    """
    if "enforce_scope" in request.keywords:
        return
    monkeypatch.setattr("pocketpaw.api.deps._TESTING_FULL_ACCESS", True)


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
