# Retrieval log — paw-runtime sink for RetrievalTrace events from soul + kb + skills.
# Created: 2026-04-13 (Move 4 PR-B) — JSONL appender, filtered reader, HTTP endpoint,
# CLI tail. Consumers: graduation policy (PR-C), Why? drawer (PR-D), compliance export.

from ee.retrieval.log import RetrievalLog, get_log
from ee.retrieval.models import RetrievalLogEntry

__all__ = ["RetrievalLog", "RetrievalLogEntry", "get_log"]
