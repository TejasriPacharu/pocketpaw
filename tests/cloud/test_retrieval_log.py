# tests/cloud/test_retrieval_log.py — Sink + reader + HTTP for Move 4 PR-B.
# Created: 2026-04-13 — Async-safe append, filter correctness, malformed-line
# tolerance, stats, HTTP wrapping.

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ee.retrieval.log import RetrievalLog, get_log, reset_log_for_tests
from ee.retrieval.router import router


def _trace(
    *,
    actor: str = "user:priya",
    source: str = "soul",
    query: str = "renewal discount",
    pocket_id: str | None = "pocket-1",
    candidates: list[dict] | None = None,
) -> dict:
    return {
        "id": "rt_" + actor[:6],
        "actor": actor,
        "query": query,
        "source": source,
        "candidates": candidates or [{"id": "m1", "source": source, "score": 0.9}],
        "picked": [],
        "used_by": None,
        "latency_ms": 12,
        "pocket_id": pocket_id,
        "timestamp": datetime.now().isoformat(),
        "metadata": {},
    }


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_log_for_tests()
    yield
    reset_log_for_tests()


@pytest.fixture
def log(tmp_path: Path) -> RetrievalLog:
    return RetrievalLog(path=tmp_path / "retrieval_test.jsonl")


# ---------------------------------------------------------------------------
# Sink
# ---------------------------------------------------------------------------


class TestSink:
    @pytest.mark.asyncio
    async def test_append_writes_jsonl_line(self, log: RetrievalLog) -> None:
        entry = await log.append(_trace())
        assert entry.actor() == "user:priya"

        contents = log.path.read_text(encoding="utf-8").splitlines()
        assert len(contents) == 1
        parsed = json.loads(contents[0])
        assert parsed["trace"]["query"] == "renewal discount"

    @pytest.mark.asyncio
    async def test_append_accepts_pydantic_trace(self, log: RetrievalLog) -> None:
        try:
            from soul_protocol.spec.retrieval import RetrievalCandidate, RetrievalTrace
        except ImportError:
            pytest.skip("soul_protocol not installed in dev env (optional dep)")

        trace = RetrievalTrace(
            actor="user:maya",
            query="oat milk",
            candidates=[RetrievalCandidate(id="m1", score=0.5)],
        )
        entry = await log.append(trace)
        assert entry.actor() == "user:maya"
        assert entry.candidate_ids() == ["m1"]

    @pytest.mark.asyncio
    async def test_append_rejects_unknown_type(self, log: RetrievalLog) -> None:
        with pytest.raises(TypeError):
            await log.append("not a trace")

    @pytest.mark.asyncio
    async def test_concurrent_appends_preserve_line_integrity(self, log: RetrievalLog) -> None:
        await asyncio.gather(*(log.append(_trace(actor=f"user:{i}")) for i in range(20)))
        lines = log.path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 20
        # Every line must be valid JSON.
        for line in lines:
            json.loads(line)


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------


class TestReader:
    @pytest.mark.asyncio
    async def test_filter_by_actor(self, log: RetrievalLog) -> None:
        await log.append(_trace(actor="user:priya"))
        await log.append(_trace(actor="user:maya"))
        await log.append(_trace(actor="user:priya"))

        rows = await log.read(actor="user:priya")
        assert len(rows) == 2
        assert all(r.actor() == "user:priya" for r in rows)

    @pytest.mark.asyncio
    async def test_filter_by_source(self, log: RetrievalLog) -> None:
        await log.append(_trace(source="soul"))
        await log.append(_trace(source="kb"))
        rows = await log.read(source="kb")
        assert len(rows) == 1
        assert rows[0].source() == "kb"

    @pytest.mark.asyncio
    async def test_filter_by_pocket_id(self, log: RetrievalLog) -> None:
        await log.append(_trace(pocket_id="pocket-1"))
        await log.append(_trace(pocket_id="pocket-2"))
        rows = await log.read(pocket_id="pocket-1")
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_filter_by_time_window(self, log: RetrievalLog) -> None:
        await log.append(_trace(actor="user:old"))
        cutoff = datetime.now() + timedelta(milliseconds=10)
        await asyncio.sleep(0.05)
        await log.append(_trace(actor="user:new"))

        recent = await log.read(since=cutoff)
        assert len(recent) == 1
        assert recent[0].actor() == "user:new"

    @pytest.mark.asyncio
    async def test_results_are_newest_first(self, log: RetrievalLog) -> None:
        await log.append(_trace(actor="user:a"))
        await asyncio.sleep(0.01)
        await log.append(_trace(actor="user:b"))
        rows = await log.read()
        assert rows[0].actor() == "user:b"
        assert rows[1].actor() == "user:a"

    @pytest.mark.asyncio
    async def test_limit_caps_results(self, log: RetrievalLog) -> None:
        for i in range(5):
            await log.append(_trace(actor=f"user:{i}"))
        rows = await log.read(limit=2)
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_missing_file_returns_empty(self, log: RetrievalLog) -> None:
        rows = await log.read()
        assert rows == []

    @pytest.mark.asyncio
    async def test_malformed_lines_are_skipped(self, log: RetrievalLog) -> None:
        await log.append(_trace(actor="user:good"))
        # Inject a malformed line directly.
        with log.path.open("a", encoding="utf-8") as fh:
            fh.write("not json at all\n")
            fh.write('{"trace": "incomplete"\n')
        await log.append(_trace(actor="user:also_good"))

        rows = await log.read()
        assert len(rows) == 2
        assert {r.actor() for r in rows} == {"user:good", "user:also_good"}


class TestTail:
    @pytest.mark.asyncio
    async def test_tail_returns_newest_last(self, log: RetrievalLog) -> None:
        for i in range(5):
            await log.append(_trace(actor=f"user:{i}"))
            await asyncio.sleep(0.005)
        tailed = await log.tail(n=3)
        assert [t.actor() for t in tailed] == ["user:2", "user:3", "user:4"]


class TestStats:
    @pytest.mark.asyncio
    async def test_stats_counts_actors_and_pockets(self, log: RetrievalLog) -> None:
        await log.append(_trace(actor="user:a", pocket_id="pocket-1"))
        await log.append(_trace(actor="user:a", pocket_id="pocket-2"))
        await log.append(_trace(actor="user:b", pocket_id="pocket-1"))
        stats = await log.stats()
        assert stats == {"total": 3, "actors": 2, "pockets": 2}

    @pytest.mark.asyncio
    async def test_stats_on_empty_log(self, log: RetrievalLog) -> None:
        stats = await log.stats()
        assert stats == {"total": 0, "actors": 0, "pockets": 0}


# ---------------------------------------------------------------------------
# Singleton + env override
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_log_returns_same_instance(self) -> None:
        a = get_log()
        b = get_log()
        assert a is b

    def test_env_override_path(self, tmp_path: Path, monkeypatch) -> None:
        custom = tmp_path / "custom_retrieval.jsonl"
        monkeypatch.setenv("POCKETPAW_RETRIEVAL_LOG", str(custom))
        reset_log_for_tests()
        log = get_log()
        assert log.path == custom


# ---------------------------------------------------------------------------
# HTTP router
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_log(tmp_path: Path):
    app = FastAPI()
    app.include_router(router)
    log = RetrievalLog(path=tmp_path / "router_test.jsonl")
    with patch("ee.retrieval.router.get_log", return_value=log):
        yield app, log


@pytest.fixture
def client(app_with_log):
    app, _ = app_with_log
    return TestClient(app)


class TestHTTPEndpoints:
    @pytest.mark.asyncio
    async def test_log_endpoint_returns_envelope(self, app_with_log, client: TestClient) -> None:
        _, log = app_with_log
        await log.append(_trace())

        res = client.get("/retrieval/log")
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 1
        assert body["entries"][0]["trace"]["query"] == "renewal discount"

    @pytest.mark.asyncio
    async def test_log_endpoint_passes_filters(self, app_with_log, client: TestClient) -> None:
        _, log = app_with_log
        await log.append(_trace(actor="user:a"))
        await log.append(_trace(actor="user:b"))

        res = client.get("/retrieval/log?actor=user%3Ab")
        body = res.json()
        assert body["total"] == 1
        assert body["entries"][0]["trace"]["actor"] == "user:b"

    @pytest.mark.asyncio
    async def test_stats_endpoint(self, app_with_log, client: TestClient) -> None:
        _, log = app_with_log
        await log.append(_trace(actor="user:a"))
        await log.append(_trace(actor="user:b"))

        res = client.get("/retrieval/stats")
        assert res.status_code == 200
        body = res.json()
        assert body == {"total": 2, "actors": 2, "pockets": 1}
