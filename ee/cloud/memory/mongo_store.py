"""MongoDB implementation of MemoryStoreProtocol backed by the unified schema.

SESSION entries are stored as pocket-context rows in the `messages` collection,
keyed by ``session_key`` (mirrors the protocol's own key). LONG_TERM and DAILY
entries live in ``memory_facts``.

Session metadata (title, lastActivity, messageCount) remains the responsibility
of the API layer (`SessionService`). This store only writes message rows —
the `sessions` collection stays user-facing / UI-owned.

Tenant scope
------------
Every row is stamped with a ``workspace_id`` so multi-tenant ee deployments
can isolate reads. For SESSION rows the adapter resolves it from the linked
Session.workspace at write time. For LONG_TERM / DAILY rows callers populate
``entry.metadata["workspace_id"]``. Reads expose ``workspace_id`` as a
parameter on the adapter-specific helpers (``list_facts_in_workspace``,
``get_session_in_workspace``); the protocol-level methods stay unscoped to
preserve the ``MemoryStoreProtocol`` contract for OSS callers.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from beanie import PydanticObjectId
from bson.errors import InvalidId

from ee.cloud.memory.documents import MemoryFactDoc
from ee.cloud.models.message import Message
from ee.cloud.models.session import Session
from pocketpaw.memory.protocol import MemoryEntry, MemoryType  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Channels the pocketpaw bus emits as the prefix of `InboundMessage.session_key`
# (``f"{channel.value}:{chat_id}"``). Kept in sync with
# ``pocketpaw.bus.events.Channel`` — when a new adapter is added there, append
# its value here. ``_normalize_session_key`` logs a warning when it sees a
# colon-form prefix it doesn't recognise so the drift is visible.
_KNOWN_BUS_CHANNELS = frozenset({"websocket", "telegram", "discord", "slack", "whatsapp", "cli"})


def _normalize_session_key(key: str) -> str:
    """Translate bus-style session keys to the underscore form used by Session.sessionId.

    The pocketpaw message bus forms session keys as ``"{channel}:{chat_id}"``
    (colon), while ``Session.sessionId`` and the UI use the safe-key form
    ``"{channel}_{chat_id}"`` (underscore). To keep ``messages.session_key``
    joinable with ``sessions.sessionId``, we rewrite the first ``":"`` to
    ``"_"`` on every read/write — but only when the prefix matches a known
    channel so unrelated keys (user-supplied pocket session keys, etc.) are
    left untouched. Unknown colon-prefixed keys log a warning so a missing
    channel is visible rather than silent.
    """
    if ":" not in key:
        return key
    channel, _, rest = key.partition(":")
    if channel in _KNOWN_BUS_CHANNELS:
        return f"{channel}_{rest}"
    logger.warning(
        "session_key %r looks bus-shaped (colon) but channel %r is not in the "
        "known list — left untouched. Update _KNOWN_BUS_CHANNELS if a new bus "
        "adapter was added.",
        key,
        channel,
    )
    return key


def _message_to_entry(msg: Message) -> MemoryEntry:
    """Translate a pocket-context Message to a protocol MemoryEntry."""
    ts = msg.createdAt or datetime.now(UTC)
    metadata: dict = {}
    if msg.workspace_id:
        metadata["workspace_id"] = msg.workspace_id
    return MemoryEntry(
        id=str(msg.id),
        type=MemoryType.SESSION,
        content=msg.content,
        created_at=ts,
        updated_at=ts,
        role=msg.role,
        session_key=msg.session_key,
        metadata=metadata,
    )


def _fact_to_entry(doc: MemoryFactDoc) -> MemoryEntry:
    """Translate a MemoryFactDoc to a protocol MemoryEntry."""
    ts_created = doc.createdAt or datetime.now(UTC)
    ts_updated = doc.updatedAt or ts_created
    metadata = dict(doc.metadata)
    if doc.user_id:
        metadata.setdefault("user_id", doc.user_id)
    if doc.workspace_id:
        metadata.setdefault("workspace_id", doc.workspace_id)
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

    Multi-tenant scoping
    ~~~~~~~~~~~~~~~~~~~~
    Every persisted row carries a ``workspace_id`` (derived from the linked
    ``Session.workspace`` for pocket messages, supplied via
    ``entry.metadata["workspace_id"]`` for facts). The protocol-level read
    methods stay tenant-agnostic to keep the ``MemoryStoreProtocol`` contract
    unchanged for OSS callers; ee callers that need strict isolation should
    use the adapter-specific ``*_in_workspace`` helpers, which add an explicit
    ``workspace_id`` filter.
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
            normalized_key = _normalize_session_key(entry.session_key)

            # Dedup against chat_persistence: the chat endpoint persists the
            # user message (with attachments) the moment it arrives, and the
            # agent loop also calls us with the same content for context.
            # Without this check both land as separate Message rows and the
            # UI renders the user's send twice on reload. Window is 30s so
            # normal re-sends of identical text still persist.
            existing = await _find_recent_twin(normalized_key, role, entry.content)
            if existing is not None:
                return str(existing.id)

            workspace_id = await _resolve_session_workspace(normalized_key, entry)
            msg = Message(
                context_type="pocket",
                session_key=normalized_key,
                role=role,  # type: ignore[arg-type]
                sender_type=sender_type,
                content=entry.content,
                workspace_id=workspace_id,
            )
            await msg.insert()
            return str(msg.id)

        # LONG_TERM / DAILY → memory_facts
        meta = dict(entry.metadata or {})
        user_id = meta.pop("user_id", None)
        workspace_id = meta.pop("workspace_id", None)
        doc = MemoryFactDoc(
            type=entry.type.value,
            content=entry.content,
            tags=list(entry.tags or []),
            user_id=user_id if isinstance(user_id, str) else None,
            workspace_id=workspace_id if isinstance(workspace_id, str) else None,
            metadata=meta,
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
        messages = await Message.find({"context_type": "pocket", "session_key": key}).to_list()
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

    async def _load_session_index_async(self) -> dict:
        """Build a session-index dict from pocket-context Session docs.

        Shape-compatible with ``FileMemoryStore._load_session_index`` so the
        ``GET /sessions/runtime`` endpoint is backend-agnostic. Returns a mapping
        ``{sessionId: {title, channel, last_activity, message_count}}`` for all
        non-deleted pocket sessions.
        """
        docs = await Session.find(
            {"context_type": "pocket", "deleted_at": None}
        ).to_list()

        index: dict[str, dict] = {}
        for doc in docs:
            session_id = doc.sessionId
            # Derive channel from the safe_key prefix (websocket_xxx → "websocket").
            channel = session_id.split("_", 1)[0] if "_" in session_id else "unknown"
            # Mongo strips tzinfo on persistence; re-anchor as UTC so the
            # serialized ISO string stays unambiguous for the frontend.
            last_activity = ""
            if doc.lastActivity:
                dt = doc.lastActivity
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                last_activity = dt.isoformat()
            index[session_id] = {
                "title": doc.title or "New Chat",
                "channel": channel,
                "last_activity": last_activity,
                "message_count": doc.messageCount,
            }
        return index

    async def get_session_with_messages(
        self, session_key: str, limit: int | None = None
    ) -> tuple[Session | None, list[MemoryEntry]]:
        """Return session metadata (if any) plus its messages in one call.

        Two queries but a single adapter entry point. When ``limit`` is None
        all messages are returned; otherwise only the most recent ``limit`` in
        ascending order.
        """
        session = await self.get_session_info(session_key)
        key = _normalize_session_key(session_key)
        query = Message.find({"context_type": "pocket", "session_key": key})
        if limit is None:
            messages = await query.sort("createdAt").to_list()
        else:
            recent = await query.sort("-createdAt").limit(limit).to_list()
            messages = list(reversed(recent))
        return session, [_message_to_entry(m) for m in messages]

    # ---- Tenant-scoped reads (ee callers should prefer these) ----------

    async def get_session_in_workspace(
        self, session_key: str, workspace_id: str
    ) -> list[MemoryEntry]:
        """Like ``get_session`` but enforces a workspace boundary.

        Returns an empty list if the session_key exists but belongs to a
        different workspace, so a leaked or guessed key cannot expose a
        tenant's messages.
        """
        key = _normalize_session_key(session_key)
        messages = (
            await Message.find(
                {
                    "context_type": "pocket",
                    "session_key": key,
                    "workspace_id": workspace_id,
                }
            )
            .sort("createdAt")
            .to_list()
        )
        return [_message_to_entry(m) for m in messages]

    async def list_facts_in_workspace(
        self,
        workspace_id: str,
        memory_type: MemoryType | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryEntry]:
        """List LONG_TERM / DAILY facts scoped to a workspace.

        Rows without a ``workspace_id`` (legacy / OSS data) are excluded so
        cross-tenant leakage is impossible by construction.
        """
        filters: dict = {"workspace_id": workspace_id}
        if memory_type is not None:
            filters["type"] = memory_type.value
        if user_id is not None:
            filters["user_id"] = user_id
        facts = await MemoryFactDoc.find(filters).sort("-createdAt").limit(limit).to_list()
        return [_fact_to_entry(f) for f in facts]


# Window for treating an existing Message as a duplicate of the current
# write. Sized to comfortably cover the save_user_message → memory.add_to_session
# race (same request, same event loop) while still letting an actual user
# resend of the identical text through.
_DEDUP_WINDOW_SECONDS = 30


async def _find_recent_twin(
    session_key: str,
    role: str,
    content: str,
) -> Message | None:
    """Return an existing Message row with the same content written recently.

    Guards against the dual-write case where the chat endpoint persists the
    message once (with attachments) and the agent loop then calls us with
    the same content for agent-context memory. The first writer wins —
    attachments and ordering on the canonical record are preserved.
    """
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(seconds=_DEDUP_WINDOW_SECONDS)
    try:
        return await Message.find_one(
            {
                "context_type": "pocket",
                "session_key": session_key,
                "role": role,
                "content": content,
                "createdAt": {"$gte": cutoff},
            }
        )
    except Exception:
        logger.exception("memory dedup lookup failed for session=%s", session_key)
        return None


async def _resolve_session_workspace(session_key: str, entry: MemoryEntry) -> str | None:
    """Best-effort lookup of the workspace for a SESSION row at write time.

    Order of preference:
    1. ``entry.metadata["workspace_id"]`` if the caller already knows it
       (e.g. an HTTP handler with the active workspace in scope).
    2. The linked ``Session.workspace`` resolved by ``sessionId == session_key``.

    Returns ``None`` when neither is available — the row stays untagged but
    still persists so OSS / single-tenant callers aren't blocked. Tenant-
    scoped reads (``get_session_in_workspace``) won't return untagged rows,
    which is the correct safe default.
    """
    md_ws = (entry.metadata or {}).get("workspace_id")
    if isinstance(md_ws, str) and md_ws:
        return md_ws
    session = await Session.find_one(Session.sessionId == session_key)
    return session.workspace if session else None
