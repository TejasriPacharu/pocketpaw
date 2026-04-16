# SPEC — Unified Sessions & Messages + MongoDB Memory Backend (ee/cloud)

**Branch:** `ee`
**Status:** draft — awaiting confirmation of §2 assumptions
**Date:** 2026-04-15
**Owner:** Rohit Kushwaha

---

## 1. Objective

Reset the ee cloud chat data layer. Replace the current split design (pocket messages in file memory, group messages in Mongo with a separate shape) with a **single unified schema**:

- One `sessions` collection — metadata for every chat (pocket or group).
- One `messages` collection — every message (agent memory or group chat), distinguished by a `context_type` discriminator.
- One `memory_facts` collection — agent long-term and daily memory (unrelated to chat messages).

In ee, the MongoDB-backed `MemoryStoreProtocol` implementation becomes the default memory backend and retires the file-based pocket-message fallback. OSS installs keep `FileMemoryStore` as default.

**Users:** operators of the ee cloud deployment. Developers get a single message/session abstraction shared across agent sessions and group chats.

**Non-goals:** channels (explicitly out per owner decision); data migration (clean slate per §2.3); vector/semantic search (file store and Mem0 still cover that path).

---

## 2. Assumptions — correct before implementation

These are load-bearing. If any is wrong, the spec needs revision before I touch code.

1. **Discriminator-based schema (option B).** Both `Session` and `Message` use a `context_type: Literal["pocket", "group"]` field. Context-specific fields are optional at the schema level and validated against `context_type` by a model validator. Not option A (all-flat-optional) and not option C (polymorphic with `data` blob).
2. **Session is rewritten too, not just Message.** Existing `ee/cloud/models/session.py` and `ee/cloud/models/message.py` are deleted and rebuilt.
3. **Clean slate — confirmed 2026-04-15.** No data migration. Only dummy data in dev DB; safe to drop and rebuild.
4. **RBAC preserved.** `require_group_action` (`ee/cloud/shared/deps.py:114-159`) still applies to `context_type == "group"` messages and related group ops. The guard is adapted to the new model, not removed.
5. **`MemoryStoreProtocol` is unchanged.** The existing protocol (`src/pocketpaw/memory/protocol.py:35-79`) stays. The MongoDB adapter translates protocol calls to reads/writes on the unified collections; SESSION entries write to `messages` (with `context_type="pocket"`), LONG_TERM/DAILY entries write to `memory_facts`.
6. **Channels are out of scope.** Per owner instruction on 2026-04-15.
7. **No web-dashboard / OSS behavior change.** Outside ee, `memory_backend="file"` remains the default; `FileMemoryStore` is unchanged.
8. **No API URL changes in v1.** Routes like `/groups/{group_id}/messages` and `/sessions/{session_id}/history` keep their paths and response shapes; only the storage layer changes beneath them.

---

## 3. Acceptance Criteria

1. Single `sessions` Beanie collection with a `context_type` discriminator covers both pocket and group sessions.
2. Single `messages` Beanie collection with a `context_type` discriminator holds every message. Pocket messages carry role/content; group messages additionally carry mentions, reactions, threading, and soft-delete.
3. New `MongoMemoryStore` implements **all** `MemoryStoreProtocol` methods (`protocol.py:35-79`).
4. In ee, `memory_backend` defaults to `"mongodb"` unless `POCKETPAW_MEMORY_BACKEND` is explicitly set. OSS default stays `"file"`.
5. `SessionService.get_history` no longer falls back to file memory for pockets — all reads go through the unified `messages` collection.
6. Existing API response shapes for `/groups/{group_id}/messages`, `/sessions/{session_id}/history`, and session listings are preserved (validated by contract tests).
7. `require_group_action` still gates group ops correctly against the new schema.
8. No OSS module imports from `ee/`. ee-only code imports are behind the `memory_backend == "mongodb"` branch in `manager.py`.
9. `ruff check`, `ruff format --check`, `mypy`, `pytest --ignore=tests/e2e` all pass.
10. Test suite covers: protocol conformance (every method), pocket vs group discrimination, group RBAC, combined session-with-messages read, separate reads, soft-delete visibility, ordering invariants.

---

## 4. Commands

```bash
uv sync --dev --extra mongodb

# Run the new + touched ee tests
uv run pytest tests/cloud/ -v

# Focused runs
uv run pytest tests/cloud/memory/ -v
uv run pytest tests/cloud/chat/ -v
uv run pytest tests/cloud/sessions/ -v

# Lint + format + types
uv run ruff check . && uv run ruff format . && uv run mypy .

# Smoke-test ee against local Mongo
POCKETPAW_MEMORY_BACKEND=mongodb \
POCKETPAW_CLOUD_MONGO_URI=mongodb://localhost:27017/paw-test \
uv run pocketpaw
```

---

## 5. Project Structure

### Collections (post-rewrite)

| Collection | Shape | Indexes |
|---|---|---|
| `sessions` | `sessionId` (unique), `context_type`, `workspace`, `owner`, `title`, `lastActivity`, `messageCount`, context-specific refs (`pocket`, `group`, `agent`), `deleted_at` | `(sessionId)` unique; `(workspace, context_type, lastActivity DESC)`; `(workspace, owner, lastActivity DESC)` |
| `messages` | `messageId` (ObjectId `_id` exposed as hex), `context_type`, `context_id` (session or group id), `session_key`, `sender`, `sender_type`, `role`, `content`, `mentions?`, `reactions?`, `reply_to?`, `attachments?`, `edited`, `deleted`, `createdAt`, `updatedAt`, `metadata` | `(context_type, context_id, createdAt DESC)`; `(session_key, createdAt ASC)` for agent memory reads |
| `memory_facts` | agent LONG_TERM / DAILY entries | `(type, user_id, createdAt DESC)`, `tags` |

**`context_type` = `"pocket"`** → `role` in {user, assistant, system}; `session_key` set; group-only fields empty.
**`context_type` = `"group"`** → `context_id` = group id; `sender`/`sender_type` required; mentions/reactions/threading allowed.

### New files

```
ee/cloud/memory/
├── __init__.py                    # re-exports MongoMemoryStore
├── mongo_store.py                 # MongoMemoryStore(MemoryStoreProtocol)
├── documents.py                   # MemoryFactDoc
└── bootstrap.py                   # register_default_backend()

tests/cloud/memory/
├── __init__.py
├── conftest.py                    # mongomock-motor + init_beanie fixture
├── test_protocol_conformance.py
├── test_session_reads.py          # combined + separate APIs
└── test_facts.py                  # LONG_TERM / DAILY
```

### Rewritten files

```
ee/cloud/models/session.py         # unified Session with context_type
ee/cloud/models/message.py         # unified Message with context_type + model_validator
ee/cloud/models/__init__.py        # ALL_DOCUMENTS updated
```

### Modified files

```
src/pocketpaw/memory/manager.py            # add "mongodb" backend branch
ee/cloud/chat/message_service.py           # read/write via unified Message
ee/cloud/chat/group_service.py             # messageCount lives on unified Session
ee/cloud/sessions/router.py                # drop file-memory fallback
ee/cloud/sessions/service.py               # history via unified messages
ee/cloud/shared/db.py                      # call register_default_backend()
ee/cloud/shared/deps.py                    # require_group_action adapted to new Message
pyproject.toml                             # add mongomock-motor to dev (confirm first)
docs/wiki/...                              # regenerated by kb hook, not hand-edited
```

### Contract tests

Snapshot tests against existing API response shapes for:
- `GET /groups/{group_id}/messages`
- `POST /groups/{group_id}/messages`
- `GET /sessions/{session_id}/history`
- `GET /sessions` list
Ensures the rewrite is storage-only, not a breaking API change.

---

## 6. Code Style

- **Discriminator validation** — `Message.context_type` gates which optional fields may be set via a Pydantic `model_validator(mode="after")`. Violations raise `ValueError` at construction.
- **Async everywhere** — `MongoMemoryStore` methods are `async def`, matching the protocol.
- **Lazy ee imports from core** — `src/pocketpaw/memory/manager.py` imports `ee.cloud.memory.mongo_store` only inside the `memory_backend == "mongodb"` branch. No top-level ee imports from OSS code.
- **IDs** — Mongo `ObjectId` as `_id`; public string id is the 24-char hex.
- **Existing error hierarchy** — raise `CloudError` subclasses (`ee/cloud/shared/errors.py`) for cloud-facing failures; `MemoryError`/`ValueError` for protocol-layer failures matching `FileMemoryStore` semantics.
- **No silent divergence** — where the new `Message` differs from the old one, callers either consume the new shape directly or go through a thin compatibility helper (no partial migrations left in flight).
- **Comments only for non-obvious invariants** — e.g. why a compound index is ordered a certain way, why `context_type` excludes certain fields. No docstrings on trivial methods. No "what" comments.
- **Ruff / mypy** — project config (line 100, E/F/I/UP, py311) applies unchanged.

---

## 7. Testing Strategy

**Framework:** pytest + `pytest-asyncio` (`asyncio_mode = "auto"`). Mongo via `mongomock-motor`, mirroring `tests/cloud/test_e2e_api.py:68-80`.

**Coverage:**

1. **Protocol conformance** — one happy-path and one edge-case test per `MemoryStoreProtocol` method. `typing.assert_type` check confirms `MongoMemoryStore` satisfies the protocol.
2. **Discriminator enforcement** — `Message(context_type="pocket", mentions=[...])` raises; `Message(context_type="group", role="user")` raises; valid pairings pass.
3. **Ordering invariants** — `get_session(session_key)` returns ascending by `createdAt`; group `/messages` returns descending by default per existing contract.
4. **Soft-delete visibility** — `deleted=true` messages hidden from group reads; hard counts in session metadata stay accurate.
5. **Session ↔ messages consistency** — `sessions.messageCount` increments on append, decrements on hard delete; `lastActivity` updates on write.
6. **Combined vs separate reads** — `get_session_with_messages(session_key)` returns the same data as `get_session_info(session_key) + get_session(session_key)`.
7. **RBAC** — `require_group_action` denies non-members on group message writes under the new schema; pocket writes bypass group guards.
8. **Backend selection** — `create_memory_store("mongodb")` returns `MongoMemoryStore`; ee bootstrap flips default iff env is unset; explicit `POCKETPAW_MEMORY_BACKEND=file` overrides ee default.
9. **API contract snapshots** — response shapes unchanged for the four endpoints listed in §5.

Out of scope for this PR: load tests, real-Mongo integration, vector/semantic search benchmarks, data migration from any prior shape.

---

## 8. Boundaries

**Always do**
- Implement the full `MemoryStoreProtocol` — no `NotImplementedError` stubs.
- Keep OSS import hygiene: nothing under `src/pocketpaw/` imports from `ee/`.
- Register Beanie documents via `ee/cloud/models/__init__.py:ALL_DOCUMENTS`.
- Preserve existing API response shapes unless the spec explicitly changes them.
- Adapt `require_group_action` to the new schema in the same PR that lands the schema change — never leave RBAC half-wired.
- Land the rewrite and its tests together; no untested method merges.

**Ask first**
- Adding runtime deps beyond `motor`/`beanie` (already in `[mongodb]` extra) or `mongomock-motor` (dev-only).
- Modifying `MemoryStoreProtocol` itself.
- Changing API URLs or response shapes.
- Deleting historical migration scripts or fixtures if any exist.

**Never do**
- Ship the unified schema without adapted RBAC guards.
- Remove group-chat features (mentions, reactions, threading, soft-delete).
- Force `motor`/`beanie` as hard deps of `pocketpaw` core.
- Bypass workspace scoping when building queries — every `sessions`/`messages` query carries `workspace` (and RBAC where applicable).
- Amend or force-push on `ee`; go through PR flow.
- Commit real Mongo URIs, license keys, or secrets.

---

## 9. Open Risks & Follow-ups

1. **Discriminator vs subtype docs.** Beanie supports discriminators cleanly, but mypy with `model_validator` can get noisy. If signal-to-noise gets bad, fall back to two docs (`PocketMessage`, `GroupMessage`) sharing a common base — same wire shape, less ergonomic for queries. Reassess during implementation.
2. **Workspace scoping on memory.** `memory_facts` has no workspace field in v1. In multi-tenant ee this is unsafe if callers don't namespace `session_key`/`user_id`. Follow-up: add `workspace_id` + enforce at the adapter layer.
3. **Wiki regeneration.** The `kb` hook rebuilds `docs/wiki/` on commits touching `ee/cloud/**`. A schema rewrite will produce a large wiki diff; review separately rather than hand-editing.
4. **Backwards compat for clients.** Paw-enterprise and other consumers rely on existing API shapes. Contract tests in §7 protect this but only cover what we assert — if a client reads a field we don't test, we may still break it. Consider sweeping all client usages before merge.
