"""MongoMemoryStore de-duplication against the chat_persistence write path.

The chat endpoint persists the user message the moment it arrives (with
attachments). The agent loop subsequently calls ``memory.add_to_session``
with the same content to seed context for the model. Without dedup both
rows end up in Mongo and the UI renders the user's send twice on reload.
"""

from __future__ import annotations

import uuid

from pocketpaw.memory.protocol import MemoryEntry, MemoryType


def _entry(session_key: str, role: str, content: str) -> MemoryEntry:
    return MemoryEntry(
        id="",
        type=MemoryType.SESSION,
        content=content,
        role=role,
        session_key=session_key,
    )


class TestDedup:
    async def test_second_save_with_same_content_reuses_existing_id(self, store):
        key = f"sess-{uuid.uuid4().hex[:8]}"

        first_id = await store.save(_entry(key, "user", "hello there"))
        # Re-saving the identical (session, role, content) within the dedup
        # window must return the SAME id — i.e. no second row was inserted.
        second_id = await store.save(_entry(key, "user", "hello there"))

        assert first_id == second_id

    async def test_different_content_is_not_deduped(self, store):
        key = f"sess-{uuid.uuid4().hex[:8]}"

        first_id = await store.save(_entry(key, "user", "first"))
        second_id = await store.save(_entry(key, "user", "second"))

        assert first_id != second_id

    async def test_different_session_is_not_deduped(self, store):
        key_a = f"sess-a-{uuid.uuid4().hex[:8]}"
        key_b = f"sess-b-{uuid.uuid4().hex[:8]}"

        first_id = await store.save(_entry(key_a, "user", "hello"))
        second_id = await store.save(_entry(key_b, "user", "hello"))

        assert first_id != second_id

    async def test_different_role_is_not_deduped(self, store):
        key = f"sess-{uuid.uuid4().hex[:8]}"

        user_id = await store.save(_entry(key, "user", "ping"))
        asst_id = await store.save(_entry(key, "assistant", "ping"))

        assert user_id != asst_id
