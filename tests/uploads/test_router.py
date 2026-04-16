from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PNG = b"\x89PNG\r\n\x1a\n" + b"body"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    """Build an app with the uploads router pointed at a tmp dir."""
    # Patch module-level globals BEFORE importing the router
    import pocketpaw.uploads.config as cfg
    import pocketpaw.api.v1.uploads as uploads_module

    root = tmp_path / "u"
    root.mkdir()

    # Rebuild module-level service against tmp dirs
    from pocketpaw.uploads.local import LocalStorageAdapter
    from pocketpaw.uploads.file_store import JSONLFileStore
    from pocketpaw.uploads.service import UploadService
    from pocketpaw.uploads.config import UploadSettings

    test_cfg = UploadSettings(local_root=root)
    test_adapter = LocalStorageAdapter(root=root)
    test_meta = JSONLFileStore(path=root / "_idx.jsonl")
    test_svc = UploadService(adapter=test_adapter, meta=test_meta, cfg=test_cfg)

    monkeypatch.setattr(uploads_module, "_SVC", test_svc)

    app = FastAPI()
    app.include_router(uploads_module.router, prefix="/api/v1")
    return TestClient(app)


def test_upload_single_roundtrip(client: TestClient):
    r = client.post(
        "/api/v1/uploads",
        files=[("files", ("cat.png", PNG, "image/png"))],
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["uploaded"]) == 1
    assert data["uploaded"][0]["filename"] == "cat.png"
    assert data["uploaded"][0]["mime"] == "image/png"
    fid = data["uploaded"][0]["id"]

    r2 = client.get(f"/api/v1/uploads/{fid}")
    assert r2.status_code == 200
    assert r2.content == PNG
    assert r2.headers["content-type"].startswith("image/png")
    assert "inline" in r2.headers["content-disposition"]


def test_bulk_upload_partial_success(client: TestClient):
    r = client.post(
        "/api/v1/uploads",
        files=[
            ("files", ("good.png", PNG, "image/png")),
            ("files", ("bad.svg", b"<svg/>", "image/svg+xml")),
        ],
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["uploaded"]) == 1
    assert len(data["failed"]) == 1
    assert data["failed"][0]["code"] == "unsupported_mime"


def test_delete_then_get_not_found(client: TestClient):
    r = client.post(
        "/api/v1/uploads",
        files=[("files", ("cat.png", PNG, "image/png"))],
    )
    fid = r.json()["uploaded"][0]["id"]

    r2 = client.delete(f"/api/v1/uploads/{fid}")
    assert r2.status_code == 204

    r3 = client.get(f"/api/v1/uploads/{fid}")
    assert r3.status_code == 404


def test_get_missing_id_is_404(client: TestClient):
    r = client.get("/api/v1/uploads/nope")
    assert r.status_code == 404


def test_docx_gets_attachment_disposition(client: TestClient):
    docx = b"PK\x03\x04" + b"rest"
    r = client.post(
        "/api/v1/uploads",
        files=[("files", (
            "doc.docx",
            docx,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ))],
    )
    fid = r.json()["uploaded"][0]["id"]
    r2 = client.get(f"/api/v1/uploads/{fid}")
    assert r2.status_code == 200
    assert "attachment" in r2.headers["content-disposition"]
