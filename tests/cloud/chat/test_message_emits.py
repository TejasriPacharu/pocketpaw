"""Tests that MessageService emits realtime events via the bus.

Each public MessageService mutation must fire the appropriate Event class
through ``emit()``. We patch the DB/permission layer at its seams so we
test the emit behavior in isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _fake_group(group_id: str = "g1", owner: str = "u1") -> SimpleNamespace:
    """Minimal Group stand-in for permission checks."""
    return SimpleNamespace(
        id=group_id,
        workspace="w1",
        owner=owner,
        members=[owner],
        member_roles={owner: "admin"},
        archived=False,
        type="group",
        last_message_at=None,
        message_count=0,
        save=AsyncMock(),
    )


def _fake_message(
    *,
    message_id: str = "m1",
    group_id: str = "g1",
    sender: str = "u1",
    content: str = "hi",
) -> SimpleNamespace:
    """Minimal Message stand-in with the attributes _message_response reads."""
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=message_id,
        group=group_id,
        sender=sender,
        sender_type="user",
        agent=None,
        content=content,
        mentions=[],
        reply_to=None,
        attachments=[],
        reactions=[],
        edited=False,
        edited_at=None,
        deleted=False,
        context_type="group",
        createdAt=now,
        insert=AsyncMock(),
        save=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_send_message_emits_new_and_sent():
    """MessageService.send_message must fire both message.new and message.sent."""
    from ee.cloud.chat.schemas import SendMessageRequest
    from ee.cloud.realtime.events import MessageNew, MessageSent

    recorded: list = []

    async def fake_emit(ev):
        recorded.append(ev)

    group = _fake_group()

    fake_msg = _fake_message(sender="u1", content="hi")

    def _fake_message_ctor(*args, **kwargs):
        # Mirror the fields send_message sets on the Message so _message_response
        # produces a sensible shape.
        fake_msg.content = kwargs.get("content", fake_msg.content)
        fake_msg.sender = kwargs.get("sender", fake_msg.sender)
        fake_msg.group = kwargs.get("group", fake_msg.group)
        return fake_msg

    with (
        patch("ee.cloud.chat.message_service.emit", new=fake_emit),
        patch(
            "ee.cloud.chat.message_service._get_group_or_404",
            new=AsyncMock(return_value=group),
        ),
        patch("ee.cloud.chat.message_service._require_can_post"),
        patch("ee.cloud.chat.message_service.event_bus.emit", new=AsyncMock()),
        patch("ee.cloud.chat.message_service.Message", new=_fake_message_ctor),
    ):
        from ee.cloud.chat.message_service import MessageService

        await MessageService.send_message("g1", "u1", SendMessageRequest(content="hi"))

    wire_types = {type(e).__name__ for e in recorded}
    assert "MessageNew" in wire_types
    assert "MessageSent" in wire_types

    # message.new payload must carry sender so AudienceResolver can exclude.
    new_ev = next(e for e in recorded if isinstance(e, MessageNew))
    assert new_ev.data.get("sender") == "u1"

    # message.sent payload must carry sender_id so AudienceResolver can address it.
    sent_ev = next(e for e in recorded if isinstance(e, MessageSent))
    assert sent_ev.data.get("sender_id") == "u1"


@pytest.mark.asyncio
async def test_edit_message_emits_edited():
    from ee.cloud.chat.schemas import EditMessageRequest
    from ee.cloud.realtime.events import MessageEdited

    recorded: list = []

    async def fake_emit(ev):
        recorded.append(ev)

    msg = _fake_message()
    group = _fake_group()

    with (
        patch("ee.cloud.chat.message_service.emit", new=fake_emit),
        patch(
            "ee.cloud.chat.message_service._get_group_message_or_404",
            new=AsyncMock(return_value=msg),
        ),
        patch(
            "ee.cloud.chat.message_service._get_group_or_404",
            new=AsyncMock(return_value=group),
        ),
        patch("ee.cloud.chat.message_service._require_can_post"),
    ):
        from ee.cloud.chat.message_service import MessageService

        await MessageService.edit_message("m1", "u1", EditMessageRequest(content="new"))

    assert any(isinstance(e, MessageEdited) for e in recorded)
    ev = next(e for e in recorded if isinstance(e, MessageEdited))
    assert ev.data["message_id"] == "m1"
    assert ev.data["group_id"] == "g1"
    assert ev.data["content"] == "new"
    assert "edited_at" in ev.data


@pytest.mark.asyncio
async def test_delete_message_emits_deleted():
    from ee.cloud.realtime.events import MessageDeleted

    recorded: list = []

    async def fake_emit(ev):
        recorded.append(ev)

    msg = _fake_message()

    with (
        patch("ee.cloud.chat.message_service.emit", new=fake_emit),
        patch(
            "ee.cloud.chat.message_service._get_group_message_or_404",
            new=AsyncMock(return_value=msg),
        ),
    ):
        from ee.cloud.chat.message_service import MessageService

        await MessageService.delete_message("m1", "u1")

    assert any(isinstance(e, MessageDeleted) for e in recorded)
    ev = next(e for e in recorded if isinstance(e, MessageDeleted))
    assert ev.data["message_id"] == "m1"
    assert ev.data["group_id"] == "g1"


@pytest.mark.asyncio
async def test_toggle_reaction_emits_message_reaction():
    from ee.cloud.realtime.events import MessageReaction

    recorded: list = []

    async def fake_emit(ev):
        recorded.append(ev)

    msg = _fake_message()
    group = _fake_group()

    with (
        patch("ee.cloud.chat.message_service.emit", new=fake_emit),
        patch(
            "ee.cloud.chat.message_service._get_group_message_or_404",
            new=AsyncMock(return_value=msg),
        ),
        patch(
            "ee.cloud.chat.message_service._get_group_or_404",
            new=AsyncMock(return_value=group),
        ),
        patch("ee.cloud.chat.message_service._require_can_post"),
    ):
        from ee.cloud.chat.message_service import MessageService

        await MessageService.toggle_reaction("m1", "u1", "\U0001f44d")

    assert any(isinstance(e, MessageReaction) for e in recorded)
    ev = next(e for e in recorded if isinstance(e, MessageReaction))
    assert ev.data["message_id"] == "m1"
    assert ev.data["group_id"] == "g1"
    assert ev.data["emoji"] == "\U0001f44d"
    assert ev.data["user_id"] == "u1"


def test_router_no_longer_broadcasts_message_events():
    """Regression guard: the four _ws_message_* handlers must not call manager.broadcast/send."""
    from pathlib import Path

    src = Path("D:/paw/backend/ee/cloud/chat/router.py").read_text(encoding="utf-8")

    start = src.index("async def _ws_message_send")
    end = src.index("async def _ws_typing")
    segment = src[start:end]
    assert "manager.broadcast_to_group" not in segment, (
        "message send/edit/delete/react handler still broadcasts directly — route via emit()"
    )
    assert "manager.send_to_user" not in segment, (
        "message handler still calls send_to_user directly"
    )
