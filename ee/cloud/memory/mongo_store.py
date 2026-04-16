"""MongoDB implementation of MemoryStoreProtocol backed by the unified schema.

SESSION entries are stored as pocket-context rows in the `messages` collection,
keyed by ``session_key`` (mirrors the protocol's own key). LONG_TERM and DAILY
entries live in ``memory_facts``.

Session metadata (title, lastActivity, messageCount) remains the responsibility
of the API layer (`SessionService`). This store only writes message rows —
the `sessions` collection stays user-facing / UI-owned.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from beanie import PydanticObjectId
from bson.errors import InvalidId

from ee.cloud.memory.documents import MemoryFactDoc
from ee.cloud.models.message import Message
from ee.cloud.models.session import Session
from pocketpaw.memory.protocol import MemoryEntry, MemoryType  # type: ignore[import-untyped]


def _normalize_session_key(key: str) -> str:
    """Normalize bus-style session keys to the underscore form used by Session.sessionId.

    The pocketpaw message bus forms session keys as ``"{channel}:{chat_id}"``
    (colon), while ``Session.sessionId`` and the UI use the safe-key form
    ``"{channel}_{chat_id}"`` (underscore). To keep ``messages.session_key``
    joinable with ``sessions.sessionId``, we rewrite the first ``":"`` to
    ``"_"`` on every read/write — but only when the prefix matches a known
    channel so unrelated keys (user-supplied pocket session keys, etc.) are
    left untouched.
    """
    if ":" not in key:
        return key
    channel, _, rest = key.partition(":")
    # Mirror the channels the bus currently emits. Keeping this list explicit
    # avoids accidentally rewriting application-level keys that contain ``":"``.
    if channel in {"websocket", "telegram", "discord", "slack", "whatsapp", "cli"}:
        return f"{channel}_{rest}"
    return key


def _message_to_entry(msg: Message) -> MemoryEntry:
    """Translate a pocket-context Message to a protocol MemoryEntry."""
    ts = msg.createdAt or datetime.now(UTC)
    return MemoryEntry(
        id=str(msg.id),
        type=MemoryType.SESSION,
        content=msg.content,
        created_at=ts,
        updated_at=ts,
        role=msg.role,
        session_key=msg.session_key,
    )


def _fact_to_entry(doc: MemoryFactDoc) -> MemoryEntry:
    """Translate a MemoryFactDoc to a protocol MemoryEntry."""
    ts_created = doc.createdAt or datetime.now(UTC)
    ts_updated = doc.updatedAt or ts_created
    metadata = dict(doc.metadata)
    if doc.user_id:
        metadata.setdefault("user_id", doc.user_id)
    return MemoryEntry(
        id=str(doc.id),
        type=MemoryType(doc.type),
        content=doc.content,
        created_at=ts_created,
        updated_at=ts_updated,
        tags=list(doc.tags),
        metadata=metadata,
    )


class MongoMemoryStore:
    """Full MemoryStoreProtocol implementation on top of the unified schema.

    - SESSION: reads/writes the `messages` collection (pocket context).
    - LONG_TERM / DAILY: reads/writes the `memory_facts` collection.

    No workspace scoping at the adapter layer — callers must namespace their
    ``session_key`` and ``user_id`` across tenants. Flagged as follow-up in
    SPEC §9.2.
    """

    async def save(self, entry: MemoryEntry) -> str:
        if entry.type == MemoryType.SESSION:
            if not entry.session_key:
                raise ValueError("SESSION entry must have session_key set")
            role = entry.role or "user"
            # `sender_type` mirrors the chat-message convention used by the
            # group-chat path: assistant rows land as "agent", everything
            # else (user/system) as "user". Without this both fields would
            # default to "user" and downstream UIs that read `senderType`
            # (instead of `role`) would render every message as the user.
            sender_type = "agent" if role == "assistant" else "user"
            msg = Message(
                context_type="pocket",
                session_key=_normalize_session_key(entry.session_key),
                role=role,  # type: ignore[arg-type]
                sender_type=sender_type,
                content=entry.content,
            )
            await msg.insert()
            return str(msg.id)

        # LONG_TERM / DAILY → memory_facts
        user_id = entry.metadata.get("user_id") if entry.metadata else None
        # Don't duplicate user_id in metadata — the column is canonical.
        metadata = {k: v for k, v in (entry.metadata or {}).items() if k != "user_id"}
        doc = MemoryFactDoc(
            type=entry.type.value,
            content=entry.content,
            tags=list(entry.tags or []),
            user_id=user_id if isinstance(user_id, str) else None,
            metadata=metadata,
        )
        await doc.insert()
        return str(doc.id)

    async def get(self, entry_id: str) -> MemoryEntry | None:
        try:
            oid = PydanticObjectId(entry_id)
        except (InvalidId, ValueError):
            return None
        msg = await Message.get(oid)
        if msg and msg.context_type == "pocket":
            return _message_to_entry(msg)
        fact = await MemoryFactDoc.get(oid)
        if fact:
            return _fact_to_entry(fact)
        return None

    async def delete(self, entry_id: str) -> bool:
        try:
            oid = PydanticObjectId(entry_id)
        except (InvalidId, ValueError):
            return False
        msg = await Message.get(oid)
        if msg and msg.context_type == "pocket":
            await msg.delete()
            return True
        fact = await MemoryFactDoc.get(oid)
        if fact:
            await fact.delete()
            return True
        return False

    async def search(
        self,
        query: str | None = None,
        memory_type: MemoryType | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        # Substring-only search (no vectors). Dispatches by type:
        # SESSION → messages; LONG_TERM/DAILY → memory_facts; None → facts
        # across both fact types (mirrors FileMemoryStore's default search).
        if memory_type == MemoryType.SESSION:
            filters: dict = {"context_type": "pocket"}
            if tags:
                raise NotImplementedError("tag search is not supported for SESSION messages in v1")
            if query:
                filters["content"] = {"$regex": re.escape(query), "$options": "i"}
            messages = await Message.find(filters).sort("-createdAt").limit(limit).to_list()
            return [_message_to_entry(m) for m in messages]

        fact_filters: dict = {}
        if memory_type is not None:
            fact_filters["type"] = memory_type.value
        if tags:
            fact_filters["tags"] = {"$in": tags}
        if query:
            fact_filters["content"] = {"$regex": re.escape(query), "$options": "i"}
        facts = await MemoryFactDoc.find(fact_filters).sort("-createdAt").limit(limit).to_list()
        return [_fact_to_entry(f) for f in facts]

    async def get_by_type(
        self,
        memory_type: MemoryType,
        limit: int = 100,
        user_id: str | None = None,
    ) -> list[MemoryEntry]:
        if memory_type == MemoryType.SESSION:
            messages = (
                await Message.find({"context_type": "pocket"})
                .sort("-createdAt")
                .limit(limit)
                .to_list()
            )
            return [_message_to_entry(m) for m in messages]

        filters: dict = {"type": memory_type.value}
        if user_id is not None:
            filters["user_id"] = user_id
        facts = await MemoryFactDoc.find(filters).sort("-createdAt").limit(limit).to_list()
        return [_fact_to_entry(f) for f in facts]

    async def get_session(self, session_key: str) -> list[MemoryEntry]:
        key = _normalize_session_key(session_key)
        messages = (
            await Message.find({"context_type": "pocket", "session_key": key})
            .sort("createdAt")
            .to_list()
        )
        return [_message_to_entry(m) for m in messages]

    async def clear_session(self, session_key: str) -> int:
        key = _normalize_session_key(session_key)
        messages = await Message.find(
            {"context_type": "pocket", "session_key": key}
        ).to_list()
        count = len(messages)
        for m in messages:
            await m.delete()
        return count

    # ---- Adapter-specific (not in MemoryStoreProtocol) ----------------

    async def get_session_info(self, session_key: str) -> Session | None:
        """Return the Session metadata row for ``session_key`` if it exists.

        The adapter never auto-creates `sessions` rows — that's the API layer's
        job (`SessionService`). A None return means no user-facing session
        metadata exists, even if messages do.
        """
        return await Session.find_one(Session.sessionId == session_key)

    async def get_session_with_messages(
        self, session_key: str, limit: int | None = None
    ) -> tuple[Session | None, list[MemoryEntry]]:
        """Return session metadata (if any) plus its messages in one call.

        Two queries but a single adapter entry point. When ``limit`` is None
        all messages are returned; otherwise only the most recent ``limit`` in
        ascending order.
        """
        session = await self.get_session_info(session_key)
        query = Message.find({"context_type": "pocket", "session_key": session_key})
        if limit is None:
            messages = await query.sort("createdAt").to_list()
        else:
            recent = await query.sort("-createdAt").limit(limit).to_list()
            messages = list(reversed(recent))
        return session, [_message_to_entry(m) for m in messages]
