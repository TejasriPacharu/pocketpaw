"""Tests for the pocketpaw agent seed + DM chat persistence with attachments.

Covers:
- ``seed_default_agent`` is idempotent and creates the expected Agent.
- ``save_user_message(chat_id, content, attachments=...)`` persists
  attachments on the Message doc.
- ``SessionService.get_history`` returns attachments per message.
- ``SessionService.list_by_agent`` filters to sessions for a given agent.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture()
async def beanie_db():
    """Isolated Beanie session for these tests (all EE documents registered)."""
    from beanie import init_beanie
    from mongomock_motor import AsyncMongoMockClient

    from ee.cloud.models import ALL_DOCUMENTS

    db_name = f"test_agent_seed_{uuid.uuid4().hex[:8]}"
    client = AsyncMongoMockClient()
    db = client[db_name]

    original = db.list_collection_names

    async def _safe(*_a, **_kw):
        return await original()

    db.list_collection_names = _safe  # type: ignore[method-assign]

    await init_beanie(database=db, document_models=list(ALL_DOCUMENTS))
    yield db


class TestSeedDefaultAgent:
    async def test_creates_agent_with_pocketpaw_slug(self, beanie_db) -> None:
        from ee.cloud.auth.core import seed_default_agent
        from ee.cloud.models.agent import Agent

        agent = await seed_default_agent(workspace_id="ws-1", owner_id="user-1")
        assert agent is not None
        assert agent.slug == "pocketpaw"
        assert agent.workspace == "ws-1"
        assert agent.owner == "user-1"

        # Confirm persisted
        found = await Agent.find_one(Agent.workspace == "ws-1", Agent.slug == "pocketpaw")
        assert found is not None

    async def test_is_idempotent(self, beanie_db) -> None:
        from ee.cloud.auth.core import seed_default_agent
        from ee.cloud.models.agent import Agent

        first = await seed_default_agent("ws-1", "user-1")
        second = await seed_default_agent("ws-1", "user-1")
        assert first is not None and second is not None
        assert first.id == second.id

        # Still only one agent for this workspace.
        count = await Agent.find(Agent.workspace == "ws-1", Agent.slug == "pocketpaw").count()
        assert count == 1

    async def test_per_workspace_agents(self, beanie_db) -> None:
        from ee.cloud.auth.core import seed_default_agent

        a1 = await seed_default_agent("ws-1", "user-1")
        a2 = await seed_default_agent("ws-2", "user-1")
        assert a1 is not None and a2 is not None
        assert a1.id != a2.id
        assert a1.workspace != a2.workspace


class TestSaveUserMessageAttachments:
    async def _session(self, beanie_db, chat_id: str = "sess-1") -> None:
        """Make a pocket session + workspace-bearing user so auto-create works."""
        from ee.cloud.models.session import Session
        from ee.cloud.models.user import User, WorkspaceMembership

        user = User(
            email="u@example.com",
            hashed_password="x",
            is_active=True,
            is_verified=True,
            is_superuser=True,
            name="u",
            workspaces=[
                WorkspaceMembership(
                    workspace="ws-1",
                    role="owner",
                )
            ],
        )
        await user.insert()
        session = Session(
            sessionId=chat_id,
            context_type="pocket",
            workspace="ws-1",
            owner=str(user.id),
            title="Chat",
        )
        await session.insert()

    async def test_attachments_persist_on_message(self, beanie_db) -> None:
        from ee.cloud.models.message import Message
        from ee.cloud.shared.chat_persistence import _session_cache, save_user_message

        _session_cache.clear()
        await self._session(beanie_db)

        attachments = [
            {
                "type": "image",
                "url": "/api/v1/uploads/abc123",
                "name": "screenshot.png",
                "meta": {"mime": "image/png", "size": 414255, "id": "abc123"},
            }
        ]
        await save_user_message("sess-1", "look at this", attachments=attachments)

        msg = await Message.find_one(
            Message.context_type == "pocket",
            Message.session_key == "sess-1",
        )
        assert msg is not None
        assert msg.content == "look at this"
        assert len(msg.attachments) == 1
        att = msg.attachments[0]
        assert att.type == "image"
        assert att.url == "/api/v1/uploads/abc123"
        assert att.name == "screenshot.png"
        assert att.meta["mime"] == "image/png"
        assert att.meta["size"] == 414255

    async def test_attachments_none_is_no_op(self, beanie_db) -> None:
        from ee.cloud.models.message import Message
        from ee.cloud.shared.chat_persistence import _session_cache, save_user_message

        _session_cache.clear()
        await self._session(beanie_db, chat_id="sess-plain")

        await save_user_message("sess-plain", "hi")

        msg = await Message.find_one(
            Message.context_type == "pocket",
            Message.session_key == "sess-plain",
        )
        assert msg is not None
        assert msg.attachments == []


class TestHistoryReturnsAttachments:
    async def test_pocket_history_exposes_attachments(self, beanie_db) -> None:
        from ee.cloud.models.message import Attachment, Message
        from ee.cloud.models.session import Session
        from ee.cloud.models.user import User, WorkspaceMembership
        from ee.cloud.sessions.service import SessionService

        user = User(
            email="u2@example.com",
            hashed_password="x",
            is_active=True,
            is_verified=True,
            is_superuser=False,
            name="u2",
            workspaces=[WorkspaceMembership(workspace="ws-1", role="member")],
        )
        await user.insert()
        session = Session(
            sessionId="hist-1",
            context_type="pocket",
            workspace="ws-1",
            owner=str(user.id),
            title="Chat",
        )
        await session.insert()

        msg = Message(
            context_type="pocket",
            session_key="hist-1",
            role="user",
            sender=str(user.id),
            sender_type="user",
            content="hi",
            attachments=[
                Attachment(
                    type="image",
                    url="/api/v1/uploads/xyz",
                    name="pic.png",
                    meta={"mime": "image/png", "size": 100},
                )
            ],
        )
        await msg.insert()

        result = await SessionService.get_history("hist-1", str(user.id))
        messages = result["messages"]
        assert len(messages) == 1
        assert "attachments" in messages[0]
        assert len(messages[0]["attachments"]) == 1
        assert messages[0]["attachments"][0]["url"] == "/api/v1/uploads/xyz"
        assert messages[0]["attachments"][0]["name"] == "pic.png"


class TestListByAgent:
    async def test_filters_sessions_to_given_agent(self, beanie_db) -> None:
        from ee.cloud.models.session import Session
        from ee.cloud.sessions.service import SessionService

        s_match = Session(
            sessionId="s1",
            context_type="pocket",
            workspace="ws-1",
            owner="user-1",
            agent="agent-A",
            title="match",
        )
        s_other = Session(
            sessionId="s2",
            context_type="pocket",
            workspace="ws-1",
            owner="user-1",
            agent="agent-B",
            title="other",
        )
        s_no_agent = Session(
            sessionId="s3",
            context_type="pocket",
            workspace="ws-1",
            owner="user-1",
            title="no agent",
        )
        for s in (s_match, s_other, s_no_agent):
            await s.insert()

        found = await SessionService.list_by_agent("ws-1", "user-1", "agent-A")
        assert len(found) == 1
        assert found[0]["sessionId"] == "s1"
        assert found[0]["agent"] == "agent-A"

    async def test_respects_soft_delete(self, beanie_db) -> None:
        from datetime import UTC, datetime

        from ee.cloud.models.session import Session
        from ee.cloud.sessions.service import SessionService

        deleted = Session(
            sessionId="s-dead",
            context_type="pocket",
            workspace="ws-1",
            owner="user-1",
            agent="agent-A",
            title="deleted",
            deleted_at=datetime.now(UTC),
        )
        await deleted.insert()

        found = await SessionService.list_by_agent("ws-1", "user-1", "agent-A")
        assert found == []
