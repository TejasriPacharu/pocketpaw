# pocketpaw/cli/retrieval.py — `pocketpaw retrieval tail|stats` (Move 4 PR-B).
# Created: 2026-04-13 — Terminal view over ~/.pocketpaw/retrieval.jsonl. Read
# only; the sink writes from the in-process runtime hooks.

from __future__ import annotations

import asyncio
from typing import Any

from pocketpaw.cli.utils import BOLD, DIM, GREEN, RESET, YELLOW, output_json, print_header


def run_retrieval_cmd(
    action: str | None = None,
    limit: int = 20,
    actor: str | None = None,
    source: str | None = None,
    pocket_id: str | None = None,
    as_json: bool = False,
) -> int:
    """Read the retrieval log from the terminal.

    ``action`` is the subcommand: ``tail`` (default) or ``stats``.
    """
    return asyncio.run(_run(action, limit, actor, source, pocket_id, as_json))


async def _run(
    action: str | None,
    limit: int,
    actor: str | None,
    source: str | None,
    pocket_id: str | None,
    as_json: bool,
) -> int:
    try:
        from ee.retrieval.log import get_log
    except ImportError:
        print(f"{YELLOW}Retrieval log not available — enterprise feature.{RESET}")
        return 1

    log = get_log()
    sub = (action or "tail").lower()

    if sub == "stats":
        stats = await log.stats()
        if as_json:
            output_json(stats)
        else:
            print_header("Retrieval Log Stats")
            print(f"  Total entries:  {BOLD}{stats['total']}{RESET}")
            print(f"  Distinct actors:  {BOLD}{stats['actors']}{RESET}")
            print(f"  Distinct pockets: {BOLD}{stats['pockets']}{RESET}\n")
        return 0

    if sub != "tail":
        print(f"{YELLOW}Unknown subcommand: {sub} (try 'tail' or 'stats').{RESET}")
        return 1

    rows = await log.read(actor=actor, source=source, pocket_id=pocket_id, limit=limit)

    if as_json:
        output_json([_row_to_payload(r) for r in rows])
        return 0

    title = "Recent Retrievals"
    filters: list[str] = []
    if actor:
        filters.append(f"actor={actor}")
    if source:
        filters.append(f"source={source}")
    if pocket_id:
        filters.append(f"pocket={pocket_id}")
    if filters:
        title += f" ({', '.join(filters)})"
    print_header(title)

    if not rows:
        print(f"  {DIM}No retrievals match.{RESET}\n")
        return 0

    # Reverse to newest-last so the terminal feels like `tail -f`.
    for entry in reversed(rows):
        trace = entry.trace
        ts = entry.ingested_at.isoformat(timespec="seconds")
        actor_label = trace.get("actor", "unknown")
        src = trace.get("source", "?")
        query = trace.get("query", "")
        n_candidates = len(trace.get("candidates") or [])
        latency = trace.get("latency_ms", 0)

        print(
            f"  {DIM}{ts}{RESET} "
            f"{GREEN}{src}{RESET} "
            f"{BOLD}{actor_label}{RESET} "
            f"q={query!r} "
            f"candidates={n_candidates} "
            f"latency={latency}ms",
        )
    print()
    return 0


def _row_to_payload(entry: Any) -> dict[str, Any]:
    return {
        "trace": entry.trace,
        "ingested_at": entry.ingested_at.isoformat(),
        "session_id": entry.session_id,
    }
