# Tests for ee/ API endpoints — Fabric + Instinct REST.
# Created: 2026-03-28

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ee.fabric.router import router as fabric_router
from ee.instinct.router import router as instinct_router
from ee.fabric.store import FabricStore
from ee.instinct.store import InstinctStore


@pytest.fixture
def app(tmp_path: Path):
    db_path = tmp_path / "test_ee.db"
    fabric = FabricStore(db_path)
    instinct = InstinctStore(db_path)

    app = FastAPI()
    app.include_router(fabric_router)
    app.include_router(instinct_router)

    # Override deps
    app.dependency_overrides = {
        __import__("ee.api", fromlist=["get_fabric_store"]).get_fabric_store: lambda: fabric,
        __import__("ee.api", fromlist=["get_instinct_store"]).get_instinct_store: lambda: instinct,
    }
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestFabricAPI:
    def test_create_and_list_types(self, client):
        resp = client.post("/api/v1/fabric/types", json={
            "name": "Customer",
            "properties": [{"name": "email", "type": "string"}],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Customer"

        resp = client.get("/api/v1/fabric/types")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_create_and_query_objects(self, client):
        # Create type
        type_resp = client.post("/api/v1/fabric/types", json={"name": "Order", "properties": []})
        type_id = type_resp.json()["id"]

        # Create objects
        client.post("/api/v1/fabric/objects", json={"type_id": type_id, "properties": {"amount": 100}})
        client.post("/api/v1/fabric/objects", json={"type_id": type_id, "properties": {"amount": 200}})

        # Query
        resp = client.get("/api/v1/fabric/objects", params={"type_name": "Order"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_link_and_traverse(self, client):
        t1 = client.post("/api/v1/fabric/types", json={"name": "Customer", "properties": []}).json()
        t2 = client.post("/api/v1/fabric/types", json={"name": "Order", "properties": []}).json()

        c = client.post("/api/v1/fabric/objects", json={"type_id": t1["id"], "properties": {"name": "Acme"}}).json()
        o = client.post("/api/v1/fabric/objects", json={"type_id": t2["id"], "properties": {"amount": 100}}).json()

        # Link
        client.post("/api/v1/fabric/links", json={
            "from_object_id": c["id"], "to_object_id": o["id"], "link_type": "has_order",
        })

        # Traverse
        resp = client.get(f"/api/v1/fabric/objects/{c['id']}/linked", params={"link_type": "has_order"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_stats(self, client):
        resp = client.get("/api/v1/fabric/stats")
        assert resp.status_code == 200
        assert "types" in resp.json()

    def test_delete_type_cascades(self, client):
        t = client.post("/api/v1/fabric/types", json={"name": "Temp", "properties": []}).json()
        client.post("/api/v1/fabric/objects", json={"type_id": t["id"], "properties": {}})

        resp = client.delete(f"/api/v1/fabric/types/{t['id']}")
        assert resp.status_code == 200

        resp = client.get("/api/v1/fabric/objects", params={"type_id": t["id"]})
        assert resp.json()["total"] == 0


class TestInstinctAPI:
    def test_propose_and_list(self, client):
        resp = client.post("/api/v1/instinct/actions", json={
            "pocket_id": "p1",
            "title": "Reorder inventory",
            "description": "Stock low",
            "recommendation": "Order 20 units",
            "trigger": {"type": "agent", "source": "claude", "reason": "threshold"},
        })
        assert resp.status_code == 201
        action = resp.json()
        assert action["status"] == "pending"

        resp = client.get("/api/v1/instinct/actions", params={"pocket_id": "p1"})
        assert len(resp.json()) == 1

    def test_approve_and_execute(self, client):
        action = client.post("/api/v1/instinct/actions", json={
            "pocket_id": "p1", "title": "Test", "recommendation": "Do it",
            "trigger": {"type": "agent", "source": "claude", "reason": "test"},
        }).json()

        resp = client.post(f"/api/v1/instinct/actions/{action['id']}/approve", json={"approver": "prakash"})
        assert resp.json()["status"] == "approved"

        resp = client.post(f"/api/v1/instinct/actions/{action['id']}/execute", json={"outcome": "Done"})
        assert resp.json()["status"] == "executed"

    def test_reject(self, client):
        action = client.post("/api/v1/instinct/actions", json={
            "pocket_id": "p1", "title": "Test", "recommendation": "Do it",
            "trigger": {"type": "agent", "source": "claude", "reason": "test"},
        }).json()

        resp = client.post(f"/api/v1/instinct/actions/{action['id']}/reject", json={"reason": "Not needed"})
        assert resp.json()["status"] == "rejected"

    def test_pending_count(self, client):
        client.post("/api/v1/instinct/actions", json={
            "pocket_id": "p1", "title": "A", "recommendation": "",
            "trigger": {"type": "agent", "source": "claude", "reason": "test"},
        })
        client.post("/api/v1/instinct/actions", json={
            "pocket_id": "p1", "title": "B", "recommendation": "",
            "trigger": {"type": "agent", "source": "claude", "reason": "test"},
        })

        resp = client.get("/api/v1/instinct/pending/count")
        assert resp.json()["count"] == 2

    def test_audit_log(self, client):
        client.post("/api/v1/instinct/actions", json={
            "pocket_id": "p1", "title": "Audited", "recommendation": "Yes",
            "trigger": {"type": "agent", "source": "claude", "reason": "test"},
        })

        resp = client.get("/api/v1/instinct/audit", params={"pocket_id": "p1"})
        assert resp.status_code == 200
        entries = resp.json()
        assert any(e["event"] == "action_proposed" for e in entries)

    def test_audit_export(self, client):
        resp = client.get("/api/v1/instinct/audit/export")
        assert resp.status_code == 200
        assert "entries" in resp.json()
