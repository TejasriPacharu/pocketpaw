# Graduation — promote frequently-accessed soul memories to higher tiers.
# Created: 2026-04-13 (Move 4 PR-C) — Reads the retrieval log written by
# ee/retrieval (PR-B), counts accesses per memory_id within a window,
# emits GraduationDecision objects when access crosses a threshold.
# Apply mode uses soul.remember() to write the higher-tier copy; the
# original entry is marked superseded via the spec's superseded field.

from ee.graduation.models import GraduationDecision, GraduationReport
from ee.graduation.policy import scan_for_graduations

__all__ = ["GraduationDecision", "GraduationReport", "scan_for_graduations"]
