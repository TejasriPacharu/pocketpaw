"""Chat persistence bridge — saves runtime WebSocket messages to MongoDB.

Contract: the WebSocket ``chat_id`` IS the ``Session.sessionId``. Clients that
want history must create a session via ``POST /api/v1/sessions`` first and
use the returned ``sessionId`` as their WS chat_id.

Messages land in the unified ``messages`` collection with ``context_type``
matching the session:

- Pocket session (default) → ``context_type="pocket"``, ``session_key=sessionId``.
- Group session (``Session.group`` set) → ``context_type="group"``,
  ``group=Session.group``. Rich features (mentions, reactions, threading)
  go through ``POST /api/v1/chat/groups/{group_id}/messages`` instead.

If no ``Session`` doc exists yet, a pocket session is auto-created so
messages have a stable key. This keeps the "start chatting, make it a
session later" experience working.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# In-memory cache of session metadata so we don't re-query Mongo on every
# message. Keyed by chat_id (== Session.sessionId).
_session_cache: dict[str, dict] = {}
# Accumulate streaming chunks per chat until stream_end.
_stream_buffers: dict[str, str] = {}


def register_chat_persistence() -> None:
    """Subscribe to the message bus to persist outbound messages to MongoDB."""
    try:
        from pocketpaw.bus.queue import get_bus

        bus = get_bus()
        if bus is None:
            logger.warning("Message bus not available, chat persistence not registered")
            return

        from pocketpaw.bus.events import Channel

        bus.subscribe_outbound(Channel.WEBSOCKET, _on_outbound_message)
        logger.info("Chat persistence bridge registered")
    except Exception:
        logger.exception("Failed to register chat persistence")


async def save_user_message(
    chat_id: str,
    content: str,
    attachments: list[dict] | None = None,
) -> None:
    """Persist a user chat message. ``chat_id`` must be the Session.sessionId.

    ``attachments``, when present, is a list of Attachment-shaped dicts
    (``{type, url, name, meta}``). They are stored on the Message doc so
    reloaded history shows the uploaded files.
    """
    try:
        ctx = await _resolve_session_context(chat_id)
        if not ctx:
            logger.warning("no session context for chat_id=%s — user message dropped", chat_id)
            return
        await _write_message(
            ctx,
            role="user",
            content=content,
            sender_type="user",
            attachments=attachments,
        )
    except Exception:
        logger.exception("Failed to persist user message")


async def _on_outbound_message(message) -> None:
    """Accumulate agent stream chunks and save final message to MongoDB."""
    try:
        chat_id = message.chat_id

        if message.is_stream_chunk:
            _stream_buffers[chat_id] = _stream_buffers.get(chat_id, "") + (message.content or "")
            return

        if message.is_stream_end:
            full_text = _stream_buffers.pop(chat_id, "")
            if not full_text.strip():
                return

            ctx = await _resolve_session_context(chat_id)
            if not ctx:
                logger.warning("no session context for chat_id=%s — agent message dropped", chat_id)
                return
            await _write_message(ctx, role="assistant", content=full_text, sender_type="agent")
            return

        # Non-streaming content accumulation
        if message.content and not message.is_stream_chunk:
            _stream_buffers[chat_id] = _stream_buffers.get(chat_id, "") + (message.content or "")
    except Exception:
        logger.exception("Failed to persist outbound message")


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _resolve_session_context(chat_id: str) -> dict | None:
    """Return the session context for a chat_id.

    Looks up (or creates) the Session doc where ``sessionId == chat_id`` and
    returns a dict describing how a message should be written:

        {
            "session_id": ObjectId hex,
            "session_key": chat_id,                 # == sessionId
            "is_group": bool,
            "group": group_id | None,               # only when is_group
            "owner": user_id,
            "workspace": workspace_id,
        }

    Returns None only when no user exists yet (fresh install, no registered
    accounts) — in that case persistence is silently skipped.
    """
    if chat_id in _session_cache:
        return _session_cache[chat_id]

    from ee.cloud.models.session import Session

    session = await Session.find_one(Session.sessionId == chat_id)
    if session is None:
        # Auto-create a pocket session so messages have a key.
        session = await _auto_create_pocket_session(chat_id)
        if session is None:
            return None

    ctx = {
        "session_id": str(session.id),
        "session_key": session.sessionId,
        "is_group": session.context_type == "group" and bool(session.group),
        "group": session.group,
        "owner": session.owner,
        "workspace": session.workspace,
    }
    _session_cache[chat_id] = ctx
    return ctx


async def _auto_create_pocket_session(chat_id: str):
    """Create a pocket Session doc for ``chat_id`` when none exists.

    Picks the first user with a workspace as owner — matches the old
    behaviour for single-user dev setups. In multi-user deployments, clients
    are expected to create sessions via ``POST /api/v1/sessions`` first.
    """
    from ee.cloud.models.session import Session
    from ee.cloud.models.user import User

    users = await User.find({"workspaces": {"$ne": []}}).limit(1).to_list()
    if not users:
        logger.warning("auto_create_pocket_session: no user with a workspace")
        return None

    user = users[0]
    workspace_id = user.workspaces[0].workspace if user.workspaces else None
    if not workspace_id:
        return None

    session = Session(
        sessionId=chat_id,
        context_type="pocket",
        workspace=workspace_id,
        owner=str(user.id),
        title="Chat",
    )
    await session.insert()
    logger.info("auto-created pocket session: sessionId=%s owner=%s", chat_id, user.id)
    return session


async def _write_message(
    ctx: dict,
    *,
    role: str,
    content: str,
    sender_type: str,
    attachments: list[dict] | None = None,
) -> None:
    """Insert a Message in the right context and touch the Session."""
    from ee.cloud.models.message import Attachment, Message
    from ee.cloud.models.session import Session

    # Coerce incoming dicts to the Attachment document model so Beanie
    # doesn't try to persist raw dicts.
    attachment_docs: list[Attachment] = []
    if attachments:
        for a in attachments:
            try:
                attachment_docs.append(Attachment(**a))
            except Exception:
                logger.warning("skipping malformed attachment on user message: %r", a)

    if ctx["is_group"]:
        msg = Message(
            context_type="group",
            group=ctx["group"],
            sender=ctx["owner"] if sender_type == "user" else None,
            sender_type=sender_type,
            content=content,
            attachments=attachment_docs,
        )
    else:
        msg = Message(
            context_type="pocket",
            session_key=ctx["session_key"],
            role=role,  # type: ignore[arg-type]
            sender=ctx["owner"] if sender_type == "user" else None,
            sender_type=sender_type,
            content=content,
            attachments=attachment_docs,
        )
    await msg.insert()

    # Touch session activity so the UI list reflects recency.
    session_doc = await Session.find_one(Session.sessionId == ctx["session_key"])
    if session_doc:
        session_doc.lastActivity = datetime.now(UTC)
        session_doc.messageCount += 1
        await session_doc.save()
