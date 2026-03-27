# Fabric API router — REST endpoints for the ontology layer.
# Created: 2026-03-28 — CRUD for object types, objects, links.

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ee.api import get_fabric_store
from ee.fabric.models import FabricQuery, PropertyDef
from ee.fabric.store import FabricStore

router = APIRouter(prefix="/api/v1/fabric", tags=["fabric"])


# --- Request Models ---

class CreateTypeRequest(BaseModel):
    name: str
    description: str = ""
    icon: str = "box"
    color: str = "#0A84FF"
    properties: list[PropertyDef] = []


class CreateObjectRequest(BaseModel):
    type_id: str
    properties: dict[str, Any] = {}
    source_connector: str | None = None
    source_id: str | None = None


class UpdateObjectRequest(BaseModel):
    properties: dict[str, Any]


class CreateLinkRequest(BaseModel):
    from_object_id: str
    to_object_id: str
    link_type: str
    properties: dict[str, Any] = {}


# --- Object Types ---

@router.get("/types")
async def list_types(store: FabricStore = Depends(get_fabric_store)):
    types = await store.list_types()
    return [t.model_dump(mode="json") for t in types]


@router.post("/types", status_code=201)
async def create_type(req: CreateTypeRequest, store: FabricStore = Depends(get_fabric_store)):
    t = await store.define_type(
        name=req.name, properties=req.properties,
        description=req.description, icon=req.icon, color=req.color,
    )
    return t.model_dump(mode="json")


@router.delete("/types/{type_id}")
async def delete_type(type_id: str, store: FabricStore = Depends(get_fabric_store)):
    existing = await store.get_type(type_id)
    if not existing:
        raise HTTPException(404, "Object type not found")
    await store.remove_type(type_id)
    return {"ok": True}


# --- Objects ---

@router.get("/objects")
async def query_objects(
    type_name: str | None = None,
    type_id: str | None = None,
    linked_to: str | None = None,
    link_type: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    store: FabricStore = Depends(get_fabric_store),
):
    q = FabricQuery(
        type_name=type_name, type_id=type_id,
        linked_to=linked_to, link_type=link_type,
        limit=limit, offset=offset,
    )
    result = await store.query(q)
    return {
        "objects": [o.model_dump(mode="json") for o in result.objects],
        "total": result.total,
    }


@router.post("/objects", status_code=201)
async def create_object(req: CreateObjectRequest, store: FabricStore = Depends(get_fabric_store)):
    obj = await store.create_object(
        type_id=req.type_id, properties=req.properties,
        source_connector=req.source_connector, source_id=req.source_id,
    )
    return obj.model_dump(mode="json")


@router.get("/objects/{obj_id}")
async def get_object(obj_id: str, store: FabricStore = Depends(get_fabric_store)):
    obj = await store.get_object(obj_id)
    if not obj:
        raise HTTPException(404, "Object not found")
    return obj.model_dump(mode="json")


@router.patch("/objects/{obj_id}")
async def update_object(obj_id: str, req: UpdateObjectRequest, store: FabricStore = Depends(get_fabric_store)):
    obj = await store.update_object(obj_id, req.properties)
    if not obj:
        raise HTTPException(404, "Object not found")
    return obj.model_dump(mode="json")


@router.delete("/objects/{obj_id}")
async def delete_object(obj_id: str, store: FabricStore = Depends(get_fabric_store)):
    existing = await store.get_object(obj_id)
    if not existing:
        raise HTTPException(404, "Object not found")
    await store.remove_object(obj_id)
    return {"ok": True}


@router.get("/objects/{obj_id}/linked")
async def get_linked(
    obj_id: str,
    link_type: str | None = None,
    store: FabricStore = Depends(get_fabric_store),
):
    objects = await store.get_linked_objects(obj_id, link_type)
    return [o.model_dump(mode="json") for o in objects]


# --- Links ---

@router.post("/links", status_code=201)
async def create_link(req: CreateLinkRequest, store: FabricStore = Depends(get_fabric_store)):
    lnk = await store.link(
        from_id=req.from_object_id, to_id=req.to_object_id,
        link_type=req.link_type, properties=req.properties,
    )
    return lnk.model_dump(mode="json")


@router.delete("/links/{link_id}")
async def delete_link(link_id: str, store: FabricStore = Depends(get_fabric_store)):
    await store.unlink(link_id)
    return {"ok": True}


# --- Stats ---

@router.get("/stats")
async def get_stats(store: FabricStore = Depends(get_fabric_store)):
    return await store.stats()
