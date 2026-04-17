"""Room-scoped routing for typing + read receipts."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_join_room_tracks_single_current_room():
    from ee.cloud.chat.ws import ConnectionManager

    mgr = ConnectionManager()
    ws = AsyncMock()
    ws.send_json = AsyncMock()

    await mgr.connect(ws, "u1")
    mgr.join_room(ws, "g1")

    assert mgr.current_room(ws) == "g1"

    # Joining a second room replaces — one room per socket
    mgr.join_room(ws, "g2")
    assert mgr.current_room(ws) == "g2"


@pytest.mark.asyncio
async def test_leave_room_clears_current_room():
    from ee.cloud.chat.ws import ConnectionManager

    mgr = ConnectionManager()
    ws = AsyncMock()
    ws.send_json = AsyncMock()

    await mgr.connect(ws, "u1")
    mgr.join_room(ws, "g1")
    mgr.leave_room(ws)

    assert mgr.current_room(ws) is None


@pytest.mark.asyncio
async def test_send_to_room_only_delivers_to_joined_sockets():
    from ee.cloud.chat.schemas import WsOutbound
    from ee.cloud.chat.ws import ConnectionManager

    mgr = ConnectionManager()

    ws_in_room = AsyncMock()
    ws_in_room.send_json = AsyncMock()
    ws_other_room = AsyncMock()
    ws_other_room.send_json = AsyncMock()
    ws_no_room = AsyncMock()
    ws_no_room.send_json = AsyncMock()

    await mgr.connect(ws_in_room, "u1")
    await mgr.connect(ws_other_room, "u2")
    await mgr.connect(ws_no_room, "u3")

    mgr.join_room(ws_in_room, "g1")
    mgr.join_room(ws_other_room, "g99")

    payload = WsOutbound(type="typing", data={"group_id": "g1", "user_id": "ux", "active": True})
    await mgr.send_to_room("g1", payload)

    ws_in_room.send_json.assert_awaited_once()
    ws_other_room.send_json.assert_not_called()
    ws_no_room.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_send_to_room_excludes_user():
    from ee.cloud.chat.schemas import WsOutbound
    from ee.cloud.chat.ws import ConnectionManager

    mgr = ConnectionManager()
    ws_sender = AsyncMock()
    ws_sender.send_json = AsyncMock()
    ws_peer = AsyncMock()
    ws_peer.send_json = AsyncMock()

    await mgr.connect(ws_sender, "u1")
    await mgr.connect(ws_peer, "u2")
    mgr.join_room(ws_sender, "g1")
    mgr.join_room(ws_peer, "g1")

    payload = WsOutbound(type="typing", data={"group_id": "g1", "user_id": "u1", "active": True})
    await mgr.send_to_room("g1", payload, exclude_user="u1")

    ws_sender.send_json.assert_not_called()
    ws_peer.send_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_clears_current_room():
    from ee.cloud.chat.ws import ConnectionManager

    mgr = ConnectionManager()
    ws = AsyncMock()
    ws.send_json = AsyncMock()

    await mgr.connect(ws, "u1")
    mgr.join_room(ws, "g1")
    await mgr.disconnect(ws)

    assert mgr.current_room(ws) is None
