# tests/cloud/test_graduation_policy.py — Move 4 PR-C.
# Created: 2026-04-13 — Threshold semantics, tier filtering, window
# enforcement, apply path with mocked soul, and the HTTP surface.

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ee.graduation.models import GraduationDecision
from ee.graduation.policy import (
    DEFAULT_EPISODIC_THRESHOLD,
    DEFAULT_SEMANTIC_THRESHOLD,
    apply_decisions,
    scan_for_graduations,
)
from ee.graduation.router import router
from ee.retrieval.log import RetrievalLog


def _trace_with_candidate(memory_id: str, *, tier: str = "episodic", actor: str = "user:priya"):
    return {
        "id": "rt_x",
        "actor": actor,
        "query": "x",
        "source": "soul",
        "candidates": [{"id": memory_id, "source": "soul", "score": 0.5, "tier": tier}],
        "picked": [],
        "used_by": None,
        "latency_ms": 1,
        "pocket_id": "pocket-1",
        "timestamp": datetime.now().isoformat(),
        "metadata": {},
    }


@pytest.fixture
def log(tmp_path: Path) -> RetrievalLog:
    return RetrievalLog(path=tmp_path / "graduation_test.jsonl")


# ---------------------------------------------------------------------------
# scan_for_graduations
# ---------------------------------------------------------------------------


class TestScan:
    @pytest.mark.asyncio
    async def test_no_decisions_when_no_log(self, log: RetrievalLog) -> None:
        report = await scan_for_graduations(log)
        assert report.decisions == []
        assert report.scanned_entries == 0
        assert report.dry_run is True

    @pytest.mark.asyncio
    async def test_episodic_promotes_at_threshold(self, log: RetrievalLog) -> None:
        for _ in range(DEFAULT_EPISODIC_THRESHOLD):
            await log.append(_trace_with_candidate("mem_renew_policy"))

        report = await scan_for_graduations(log)
        assert len(report.decisions) == 1
        decision = report.decisions[0]
        assert decision.memory_id == "mem_renew_policy"
        assert decision.kind == "episodic_to_semantic"
        assert decision.access_count == DEFAULT_EPISODIC_THRESHOLD
        assert decision.from_tier == "episodic"
        assert decision.to_tier == "semantic"

    @pytest.mark.asyncio
    async def test_below_threshold_yields_no_decision(self, log: RetrievalLog) -> None:
        for _ in range(DEFAULT_EPISODIC_THRESHOLD - 1):
            await log.append(_trace_with_candidate("mem_x"))
        report = await scan_for_graduations(log)
        assert report.decisions == []

    @pytest.mark.asyncio
    async def test_semantic_promotes_to_core_at_higher_threshold(
        self, log: RetrievalLog
    ) -> None:
        for _ in range(DEFAULT_SEMANTIC_THRESHOLD):
            await log.append(_trace_with_candidate("mem_core_fact", tier="semantic"))

        report = await scan_for_graduations(log)
        assert len(report.decisions) == 1
        d = report.decisions[0]
        assert d.kind == "semantic_to_core"
        assert d.from_tier == "semantic"
        assert d.to_tier == "core"

    @pytest.mark.asyncio
    async def test_outside_window_is_ignored(self, log: RetrievalLog) -> None:
        # Pre-write old entries by editing the file directly.
        import json

        from ee.retrieval.models import RetrievalLogEntry

        old = datetime.now() - timedelta(days=60)
        for _ in range(DEFAULT_EPISODIC_THRESHOLD):
            entry = RetrievalLogEntry(
                trace=_trace_with_candidate("mem_old"),
                ingested_at=old,
            )
            with log.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry.model_dump(mode="json")) + "\n")

        # Hits inside the window but not enough to cross threshold:
        for _ in range(DEFAULT_EPISODIC_THRESHOLD - 1):
            await log.append(_trace_with_candidate("mem_old"))

        report = await scan_for_graduations(log, window_days=30)
        assert report.decisions == []

    @pytest.mark.asyncio
    async def test_actor_filter_isolates_counts(self, log: RetrievalLog) -> None:
        for _ in range(DEFAULT_EPISODIC_THRESHOLD):
            await log.append(_trace_with_candidate("mem_x", actor="user:priya"))
        for _ in range(DEFAULT_EPISODIC_THRESHOLD):
            await log.append(_trace_with_candidate("mem_x", actor="user:maya"))

        priya_only = await scan_for_graduations(log, actor="user:priya")
        # mem_x has 10 accesses by priya alone — promotes.
        assert any(d.memory_id == "mem_x" for d in priya_only.decisions)


# ---------------------------------------------------------------------------
# apply_decisions
# ---------------------------------------------------------------------------


class TestApply:
    @pytest.mark.asyncio
    async def test_apply_calls_remember_with_target_tier(self) -> None:
        # Mock soul that surfaces a single matching entry on recall().
        soul = MagicMock()
        soul.remember = AsyncMock(return_value="mem_new_id")

        async def fake_recall(query, *, limit=500):
            entry = MagicMock()
            entry.id = "mem_x"
            entry.content = "the renewal policy caps discount at 20%"
            return [entry]

        soul.recall = fake_recall

        decision = GraduationDecision(
            memory_id="mem_x",
            kind="episodic_to_semantic",
            access_count=15,
            window_days=30,
            from_tier="episodic",
            to_tier="semantic",
            reason="threshold crossed",
        )

        applied = await apply_decisions(soul, [decision])
        assert len(applied) == 1
        soul.remember.assert_awaited_once()
        kwargs = soul.remember.await_args.kwargs
        assert "renewal policy" in kwargs["content"]
        # Importance bumps for the new tier.
        assert kwargs["importance"] >= 7

    @pytest.mark.asyncio
    async def test_apply_skips_when_memory_not_found(self) -> None:
        soul = MagicMock()
        soul.remember = AsyncMock()

        async def empty_recall(query, *, limit=500):
            return []

        soul.recall = empty_recall

        decision = GraduationDecision(
            memory_id="missing",
            kind="episodic_to_semantic",
            access_count=15,
            window_days=30,
            from_tier="episodic",
            to_tier="semantic",
        )

        applied = await apply_decisions(soul, [decision])
        assert applied == []
        soul.remember.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_apply_swallows_per_decision_errors(self) -> None:
        soul = MagicMock()
        soul.remember = AsyncMock(side_effect=RuntimeError("boom"))

        async def fake_recall(query, *, limit=500):
            entry = MagicMock()
            entry.id = "mem_x"
            entry.content = "x"
            return [entry]

        soul.recall = fake_recall

        decision = GraduationDecision(
            memory_id="mem_x",
            kind="episodic_to_semantic",
            access_count=15,
            window_days=30,
            from_tier="episodic",
            to_tier="semantic",
        )

        # Must not raise — graduation never breaks the runtime.
        applied = await apply_decisions(soul, [decision, decision])
        assert applied == []

    @pytest.mark.asyncio
    async def test_apply_returns_empty_when_soul_lacks_apis(self) -> None:
        soul = MagicMock(spec=[])  # no remember / recall attrs
        decision = GraduationDecision(
            memory_id="mem_x",
            kind="episodic_to_semantic",
            access_count=15,
            window_days=30,
            from_tier="episodic",
            to_tier="semantic",
        )
        applied = await apply_decisions(soul, [decision])
        assert applied == []


# ---------------------------------------------------------------------------
# HTTP router
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_log(tmp_path: Path):
    app = FastAPI()
    app.include_router(router)
    log = RetrievalLog(path=tmp_path / "router_grad.jsonl")
    with patch("ee.graduation.router.get_log", return_value=log):
        yield app, log


@pytest.fixture
def client(app_with_log):
    app, _ = app_with_log
    return TestClient(app)


class TestHTTPEndpoints:
    @pytest.mark.asyncio
    async def test_scan_endpoint_returns_decisions(
        self, app_with_log, client: TestClient
    ) -> None:
        _, log = app_with_log
        for _ in range(DEFAULT_EPISODIC_THRESHOLD):
            await log.append(_trace_with_candidate("mem_x"))

        res = client.post("/graduation/scan", json={})
        assert res.status_code == 200
        body = res.json()
        assert body["dry_run"] is True
        assert len(body["decisions"]) == 1
        assert body["decisions"][0]["memory_id"] == "mem_x"

    def test_apply_endpoint_returns_503_when_no_soul(self, client: TestClient) -> None:
        res = client.post("/graduation/apply", json={"decisions": []})
        # No soul manager available in test app → 503.
        assert res.status_code == 503