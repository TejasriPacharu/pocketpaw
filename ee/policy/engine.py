# ee/policy/engine.py — Apply scope tags to runtime objects.
# Created: 2026-04-13 (Move 5 PR-B) — Wraps soul-protocol's match_scope so
# every paw-runtime retrieval path uses the same matcher. Defensively reads
# `scope` from any entity (FabricObject, Pocket, MemoryEntry, dict) so new
# entity types can adopt scope tags without changing the engine.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Default behaviour: unscoped entities (scope == []) are visible to everyone.
# Set to False at startup if your tenant requires explicit scope on every
# entity. Per-call overrides via filter_visible(allow_unscoped=...).
DEFAULT_ALLOW_UNSCOPED = True


@dataclass
class PolicyDecision:
    """Result of applying the policy to a single entity."""

    allowed: bool
    entity_id: str
    entity_scopes: list[str]
    matched_scope: str | None = None
    reason: str = ""


def visible(
    entity: Any,
    user_scopes: list[str] | None,
    *,
    allow_unscoped: bool = DEFAULT_ALLOW_UNSCOPED,
) -> bool:
    """Return True when the user is allowed to see this entity.

    ``entity`` is anything with a ``scope`` attribute or a ``scope`` key —
    FabricObject, Pocket, MemoryEntry, dict, or a duck-typed stand-in.
    ``user_scopes`` is the caller's scope list. Empty/None passes through
    (caller sees everything they otherwise would).
    """
    entity_scopes = _entity_scopes(entity)

    if not user_scopes:
        return True
    if not entity_scopes:
        return allow_unscoped

    return _match(entity_scopes, user_scopes)


def filter_visible(
    entities: list[Any],
    user_scopes: list[str] | None,
    *,
    allow_unscoped: bool = DEFAULT_ALLOW_UNSCOPED,
) -> tuple[list[Any], int]:
    """Return ``(visible_entities, hidden_count)`` for the given user.

    The hidden count is what paw-runtime writes into the retrieval log so
    operators can see how many entries were filtered out per call.
    """
    if not user_scopes:
        return list(entities), 0

    kept: list[Any] = []
    hidden = 0
    for entity in entities:
        if visible(entity, user_scopes, allow_unscoped=allow_unscoped):
            kept.append(entity)
        else:
            hidden += 1
    return kept, hidden


def decide(
    entity: Any,
    user_scopes: list[str] | None,
    *,
    allow_unscoped: bool = DEFAULT_ALLOW_UNSCOPED,
) -> PolicyDecision:
    """Return a PolicyDecision explaining why the entity was allowed/denied.

    Used by the audit path so operators can answer "why was X filtered?"
    without re-running the policy.
    """
    entity_scopes = _entity_scopes(entity)
    entity_id = _entity_id(entity)

    if not user_scopes:
        return PolicyDecision(
            allowed=True,
            entity_id=entity_id,
            entity_scopes=entity_scopes,
            reason="caller has no scope filter — pass-through",
        )

    if not entity_scopes:
        return PolicyDecision(
            allowed=allow_unscoped,
            entity_id=entity_id,
            entity_scopes=entity_scopes,
            reason=(
                "entity is unscoped — allowed by default"
                if allow_unscoped
                else "entity is unscoped — denied because allow_unscoped=False"
            ),
        )

    matched = _first_match(entity_scopes, user_scopes)
    if matched is not None:
        return PolicyDecision(
            allowed=True,
            entity_id=entity_id,
            entity_scopes=entity_scopes,
            matched_scope=matched,
            reason=f"caller has '{matched}' which grants entity scope",
        )

    return PolicyDecision(
        allowed=False,
        entity_id=entity_id,
        entity_scopes=entity_scopes,
        reason="no caller scope grants any entity scope",
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _entity_scopes(entity: Any) -> list[str]:
    if entity is None:
        return []
    raw = getattr(entity, "scope", None)
    if raw is None and isinstance(entity, dict):
        raw = entity.get("scope")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    return [s for s in raw if isinstance(s, str)]


def _entity_id(entity: Any) -> str:
    if entity is None:
        return ""
    raw = getattr(entity, "id", None)
    if raw is None and isinstance(entity, dict):
        raw = entity.get("id")
    return str(raw) if raw else ""


def _match(entity_scopes: list[str], user_scopes: list[str]) -> bool:
    """Boolean OR over cartesian — same logic soul-protocol uses, replicated
    locally so paw-runtime doesn't take a hard dep on soul-protocol being
    installed for the policy engine to work.
    """
    return any(_granted(e, a) for e in entity_scopes for a in user_scopes)


def _first_match(entity_scopes: list[str], user_scopes: list[str]) -> str | None:
    for a in user_scopes:
        for e in entity_scopes:
            if _granted(e, a):
                return a
    return None


def _granted(entity_scope: str, allowed_scope: str) -> bool:
    if allowed_scope == "*":
        return True
    if allowed_scope == entity_scope:
        return True
    if allowed_scope.endswith(":*"):
        prefix = allowed_scope[:-2]
        return entity_scope == prefix or entity_scope.startswith(prefix + ":")
    return False
