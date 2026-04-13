# ee/graduation/policy.py — Tier promotion policy over the retrieval log.
# Created: 2026-04-13 (Move 4 PR-C) — Scans ~/.pocketpaw/retrieval.jsonl,
# counts access per memory_id within `window_days`, emits decisions when
# counts cross thresholds. Generalises the bespoke 3x-same-path rule from
# correction_soul_bridge — that bridge becomes a special case once the
# refactor lands post-merge.

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from ee.graduation.models import GraduationDecision, GraduationReport
from ee.retrieval.log import RetrievalLog

logger = logging.getLogger(__name__)


# Defaults — overridable per-call. Sized for "feels like learning" without
# hyperactive promotion: 10 accesses in a month for episodic→semantic,
# 50 for semantic→core. Tunable from settings or env.
DEFAULT_WINDOW_DAYS = 30
DEFAULT_EPISODIC_THRESHOLD = 10
DEFAULT_SEMANTIC_THRESHOLD = 50


async def scan_for_graduations(
    log: RetrievalLog,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    episodic_threshold: int = DEFAULT_EPISODIC_THRESHOLD,
    semantic_threshold: int = DEFAULT_SEMANTIC_THRESHOLD,
    actor: str | None = None,
    pocket_id: str | None = None,
    dry_run: bool = True,
) -> GraduationReport:
    """Scan the retrieval log and return graduation decisions.

    Each decision describes a tier change a higher process can apply. When
    ``dry_run=True`` (default) no soul mutation happens — the report is the
    full output. Apply path lives in ``apply_decisions()`` and is opt-in.

    Args:
        log: The retrieval log instance to scan.
        window_days: Look-back window for access counting.
        episodic_threshold: Accesses needed for episodic→semantic promotion.
        semantic_threshold: Accesses needed for semantic→core promotion.
        actor: Optional filter — only count accesses by this actor.
        pocket_id: Optional filter — only count accesses in this pocket.
        dry_run: When True (default), the returned report is the full output.

    Returns:
        :class:`GraduationReport` — decisions + scan metadata.
    """
    since = datetime.now() - timedelta(days=window_days)
    entries = await log.read(actor=actor, pocket_id=pocket_id, since=since, limit=10_000)

    # Per memory_id: count + most-recent tier seen + sample actor/pocket
    counts: Counter[str] = Counter()
    contexts: dict[str, dict[str, Any]] = {}

    for entry in entries:
        candidates = entry.trace.get("candidates") or []
        for cand in candidates:
            mid = cand.get("id")
            if not isinstance(mid, str):
                continue
            counts[mid] += 1
            existing = contexts.setdefault(
                mid,
                {
                    "tier": cand.get("tier"),
                    "actor": entry.actor(),
                    "pocket_id": entry.pocket_id(),
                },
            )
            # Last-seen tier wins so we reflect the current state.
            if cand.get("tier"):
                existing["tier"] = cand["tier"]

    decisions: list[GraduationDecision] = []
    for mid, count in counts.most_common():
        ctx = contexts.get(mid, {})
        from_tier = ctx.get("tier")
        decision = _decide(
            memory_id=mid,
            count=count,
            from_tier=from_tier,
            actor=ctx.get("actor", ""),
            pocket_id=ctx.get("pocket_id"),
            episodic_threshold=episodic_threshold,
            semantic_threshold=semantic_threshold,
            window_days=window_days,
        )
        if decision is not None:
            decisions.append(decision)

    return GraduationReport(
        decisions=decisions,
        scanned_entries=len(entries),
        window_days=window_days,
        dry_run=dry_run,
    )


def _decide(
    *,
    memory_id: str,
    count: int,
    from_tier: str | None,
    actor: str,
    pocket_id: str | None,
    episodic_threshold: int,
    semantic_threshold: int,
    window_days: int,
) -> GraduationDecision | None:
    """Return a decision when access count crosses a threshold for this tier."""
    tier = (from_tier or "").lower()

    if tier in {"episodic", ""} and count >= episodic_threshold:
        # Empty tier is treated as episodic — soul defaults episodic for
        # interaction-derived memories, and the retrieval log doesn't always
        # carry tier on every candidate.
        return GraduationDecision(
            memory_id=memory_id,
            actor=actor,
            pocket_id=pocket_id,
            kind="episodic_to_semantic",
            access_count=count,
            window_days=window_days,
            from_tier=from_tier or "episodic",
            to_tier="semantic",
            reason=(
                f"Accessed {count}x in last {window_days} days "
                f"(threshold {episodic_threshold})."
            ),
        )

    if tier == "semantic" and count >= semantic_threshold:
        return GraduationDecision(
            memory_id=memory_id,
            actor=actor,
            pocket_id=pocket_id,
            kind="semantic_to_core",
            access_count=count,
            window_days=window_days,
            from_tier="semantic",
            to_tier="core",
            reason=(
                f"Accessed {count}x in last {window_days} days "
                f"(threshold {semantic_threshold})."
            ),
        )

    return None


async def apply_decisions(
    soul: Any,
    decisions: list[GraduationDecision],
) -> list[GraduationDecision]:
    """Apply graduation decisions by writing higher-tier copies via soul.remember().

    Returns the subset of decisions that were applied successfully. Errors are
    logged but never raise — graduation must never break the runtime. Original
    memory entries are not deleted; soul-protocol's ``superseded`` field on
    ``MemoryEntry`` can mark the old row in a follow-up if/when the spec
    exposes a native ``promote()``.
    """
    if not hasattr(soul, "remember") or not hasattr(soul, "recall"):
        logger.debug("apply_decisions: soul has no remember/recall — skipping")
        return []

    target_type_for_tier = _resolve_tier_resolver()

    applied: list[GraduationDecision] = []
    for decision in decisions:
        try:
            content = await _lookup_memory_content(soul, decision.memory_id)
            if not content:
                logger.debug(
                    "apply_decisions: memory %s not found in soul — skipping",
                    decision.memory_id,
                )
                continue

            target_type = target_type_for_tier(decision.to_tier)
            await soul.remember(
                content=f"[graduated:{decision.kind}] {content}",
                type=target_type,
                importance=8 if decision.to_tier == "core" else 7,
            )
            applied.append(decision)
        except Exception:
            logger.exception(
                "apply_decisions: failed to graduate %s",
                decision.memory_id,
            )
    return applied


def _resolve_tier_resolver():
    """Return a callable that maps a tier name to soul-protocol's MemoryType enum.

    When soul-protocol isn't installed (rare in production, common in tests
    that mock the soul interface), fall back to passing the tier name as a
    plain string. The mock soul doesn't care about the type either way.
    """
    try:
        from soul_protocol.runtime.types import MemoryType
    except ImportError:
        return lambda tier: tier

    def _lookup(tier: str):
        try:
            return MemoryType(tier)
        except ValueError:
            return MemoryType.SEMANTIC

    return _lookup


async def _lookup_memory_content(soul: Any, memory_id: str) -> str:
    """Best-effort lookup — soul-protocol doesn't expose a get-by-id API yet.

    Pulls a wide recall and finds the matching entry. Once soul-protocol gains
    a direct lookup, swap this for a single-call read.
    """
    try:
        memories = await soul.recall("", limit=500)
    except Exception:
        return ""
    for entry in memories:
        if getattr(entry, "id", None) == memory_id:
            return getattr(entry, "content", "")
    return ""
