# Policy — RBAC/ABAC scope evaluation for paw-runtime retrieval paths.
# Created: 2026-04-13 (Move 5 PR-B) — One pure function `visible(entity, user)`
# applied at every retrieval boundary (Fabric, Pocket, soul recall, kb search).
# Scope semantics live in soul-protocol's match_scope; this module just
# applies them consistently to the runtime's data shapes.

from ee.policy.engine import (
    DEFAULT_ALLOW_UNSCOPED,
    PolicyDecision,
    filter_visible,
    visible,
)

__all__ = [
    "DEFAULT_ALLOW_UNSCOPED",
    "PolicyDecision",
    "filter_visible",
    "visible",
]
