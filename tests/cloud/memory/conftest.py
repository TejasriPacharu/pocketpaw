"""Fixtures for MongoMemoryStore tests.

Uses a real MongoDB on localhost — matches the pattern in
tests/cloud/test_e2e_api.py. Each test gets a uniquely-named database that is
dropped on teardown.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture()
async def beanie_memory_db():
    """Initialize Beanie against a throwaway test database for each test."""
    from beanie import init_beanie
    from motor.motor_asyncio import AsyncIOMotorClient

    from ee.cloud.memory.documents import MemoryFactDoc
    from ee.cloud.models import ALL_DOCUMENTS

    db_name = f"test_memory_{uuid.uuid4().hex[:8]}"
    conn_str = f"mongodb://localhost:27017/{db_name}"
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    await init_beanie(
        connection_string=conn_str,
        document_models=[*ALL_DOCUMENTS, MemoryFactDoc],
    )
    yield client[db_name]
    await client.drop_database(db_name)


@pytest.fixture()
async def store(beanie_memory_db):
    """A fresh MongoMemoryStore bound to the per-test database."""
    from ee.cloud.memory.mongo_store import MongoMemoryStore

    return MongoMemoryStore()
