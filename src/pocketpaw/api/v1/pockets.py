# Pocket chat router — dedicated endpoint for pocket creation.
# Updated: system prompt now teaches Ripple UniversalSpec v2.0 format
# with intent='dashboard'. SSE parser updated to detect both legacy
# and new pocket-spec markers. Also detects pocket-mutation markers
# for AddWidgetTool / RemoveWidgetTool.

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from pocketpaw.api.deps import require_scope
from pocketpaw.api.v1.schemas.chat import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Pockets"],
    dependencies=[Depends(require_scope("chat"))],
)

_WS_PREFIX = "websocket_"

# Match the JSON arg passed to create_pocket in a Bash command
_CREATE_POCKET_RE = re.compile(r"create_pocket\s+'(.*?)'", re.DOTALL)
# Match pocket-spec markers in tool results (UniversalSpec or legacy)
_POCKET_SPEC_RE = re.compile(r"<!-- pocket-spec:(.*?):pocket-spec -->", re.DOTALL)
# Match pocket-mutation markers from AddWidgetTool / RemoveWidgetTool
_POCKET_MUTATION_RE = re.compile(r"<!-- pocket-mutation:(.*?):pocket-mutation -->", re.DOTALL)

_POCKET_SYSTEM_CONTEXT = """\
<pocket-creation-context>
You are running inside PocketPaw OS, a desktop workspace app.
The user wants a "pocket" — a themed workspace with data widgets.

RULES:
1. Do in-depth research FIRST using a MULTI-AGENT approach:
   - Spawn PARALLEL web_search calls for different aspects of the topic.
   - For a company: run separate searches for financials, products, leadership, news, competitors.
   - For a topic: run separate searches for stats, trends, key players, recent events, forecasts.
   - Aim for 4-6 parallel searches covering distinct angles. Do NOT do one search at a time.
   - After initial results, do follow-up searches to fill gaps or verify numbers.
2. Use ONLY these tools for pocket operations:
   - create_pocket: Create a new pocket (pass the full JSON spec)
   - add_widget: Add a widget to an EXISTING pocket (pass pocket_id + widget spec)
   - remove_widget: Remove a widget from an EXISTING pocket (pass pocket_id + widget_id)
3. NEVER use curl, fetch, HTTP requests, or REST API calls to manage pockets.
   NEVER try to access /api/v1/pockets or any HTTP endpoints. Use the tools above.
4. NEVER create HTML files or write files to disk.
4. Every widget MUST have real, concrete data values — never leave data empty, null,
   or with placeholder text like "N/A", "TBD", or "...". If you cannot find a specific
   number, use your best estimate and note it with "~" prefix (e.g. "~$5B").
5. Charts MUST have at least 3 data points with numeric values > 0.
6. Tables MUST have at least 2 rows of real data.
7. Feeds MUST have at least 3 items with actual text content.

MULTI-AGENT RESEARCH WORKFLOW:
Think of yourself as orchestrating a research team. Each search covers one aspect:
  Agent 1 (Financials): revenue, valuation, funding, P&L
  Agent 2 (Products):   product lineup, features, pricing, market position
  Agent 3 (People):     leadership team, key hires, board members
  Agent 4 (News):       latest announcements, press, milestones
  Agent 5 (Market):     competitors, market share, industry trends
Run these in parallel, then synthesize findings into a comprehensive pocket.

RESEARCH STRATEGY:
- For companies: search for financials, latest news, products, leadership, competitors
- For topics: search for key stats, recent developments, major players, trends
- For industries: search for market size, growth rate, top companies, emerging trends
- Cross-reference multiple sources for accuracy

The create_pocket tool accepts these parameters and returns a Ripple UniversalSpec (v2.0):
{
  "title": "Company Analysis",
  "description": "Research overview",
  "category": "research",
  "color": "#0A84FF",
  "logo": "https://cdn.simpleicons.org/companyname/white",
  "columns": 3,
  "widgets": [
    {
      "type": "metric",
      "title": "Revenue",
      "size": "sm",
      "data": {"value": "$10B", "label": "Annual Revenue (2025)", "trend": "+15% YoY"}
    },
    {
      "type": "chart",
      "title": "Revenue Over Time",
      "size": "md",
      "data": [{"label": "Q1", "value": 2400}, {"label": "Q2", "value": 3100}, {"label": "Q3", "value": 3800}, {"label": "Q4", "value": 4500}],
      "props": {"type": "area", "height": 220}
    },
    {
      "type": "table",
      "title": "Key People",
      "size": "lg",
      "data": {"columns": ["Name", "Role", "Background"], "data": [["Alice", "CEO", "Ex-Google VP"], ["Bob", "CTO", "Stanford CS PhD"]]}
    },
    {
      "type": "feed",
      "title": "Recent News",
      "size": "md",
      "data": {"items": [{"text": "Launched v2.0 with 10x performance", "time": "2h ago", "type": "success"}, {"text": "Raised $500M Series D at $8B valuation", "time": "1d ago", "type": "info"}]}
    }
  ]
}

Widget types:
- metric: single KPI. data: {value, label, trend?}. value MUST be a concrete number/amount.
- chart: bar/line/area/pie. data: [{label, value}] (min 3 items, value MUST be numeric > 0). props: {type, height?}
- table: data grid. data: {columns: [str], data: [[cell, ...]]} (min 2 rows, cells MUST NOT be empty).
- feed: event list. data: {items: [{text, time?, type?}]} (min 3 items, text MUST be substantive).
- terminal: log output. data: {lines: [{text, type?, timestamp?}]}, props: {title?}
- text: markdown. data: {content: "markdown string"}

Widget sizes: "sm" (1 col), "md" (2 cols), "lg" (full width)

Logo: When creating a pocket for a known company or brand, include a "logo" field with their
icon URL from https://cdn.simpleicons.org/{brand-slug}/{color-hex-without-hash}
(e.g. "https://cdn.simpleicons.org/stripe/white", "https://cdn.simpleicons.org/slack/white").
For generic/non-brand pockets, omit the logo field.

Create 6-8 widgets with REAL data from your research. Prioritize metrics and charts first.

MODIFYING EXISTING POCKETS:
When a <current-pocket> tag is present in the user message, you are editing that pocket.
- To ADD a widget: call add_widget with the pocket id and the widget spec (same format as above).
- To REMOVE a widget: call remove_widget with the pocket id and the widget id.
- To RECREATE the entire pocket: call create_pocket with all widgets (replaces the current spec).
- The pocket id and widget ids are provided in the <current-pocket> tag.
- Do NOT use HTTP/curl/fetch — only use the tools listed above.
</pocket-creation-context>

"""


def _extract_chat_id(session_id: str | None) -> str:
    if session_id and session_id.startswith(_WS_PREFIX):
        return session_id[len(_WS_PREFIX) :]
    return session_id or uuid.uuid4().hex


def _to_safe_key(chat_id: str) -> str:
    if chat_id.startswith(_WS_PREFIX):
        return chat_id
    return f"{_WS_PREFIX}{chat_id}"


def _try_extract_pocket_from_bash(command: str) -> dict | None:
    """Extract pocket spec JSON from a create_pocket Bash command."""
    match = _CREATE_POCKET_RE.search(command)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        return None


def _prepare_pocket_spec(spec: dict) -> dict | None:
    """Validate AI spec and transform into Ripple-ready UniversalSpec v2.0.

    This is the SINGLE place that converts raw LLM output into the exact format
    that Ripple's DashboardRenderer expects. The client renders it as-is.

    Returns a complete, render-ready spec or None if the spec is unusable.
    """
    if not isinstance(spec, dict):
        return None

    name = spec.get("title") or spec.get("name")
    if not name:
        return None

    raw_widgets = spec.get("widgets")
    if not isinstance(raw_widgets, list) or len(raw_widgets) == 0:
        return None

    pocket_id = spec.get("id") or f"pocket-{uuid.uuid4().hex[:8]}"
    color = spec.get("color") or "#0A84FF"
    meta = spec.get("metadata") or {}

    widgets = []
    for i, w in enumerate(raw_widgets):
        if not isinstance(w, dict):
            continue

        wtype = w.get("type", "text")
        data = w.get("data")
        title = w.get("title") or w.get("name") or f"Widget {i + 1}"
        wid = w.get("id") or f"{pocket_id}-w{i}"

        # Skip widgets with no data
        if data is None:
            logger.warning("Dropping widget %r: no data", title)
            continue

        # Build the Ripple-ready widget
        rw: dict = {
            "id": wid,
            "type": wtype,
            "title": title,
            "size": w.get("size", "sm"),
            "props": {**(w.get("props") or {}), "color": w.get("color") or color},
        }

        # ── Transform data per type into exactly what Ripple components expect ──

        if wtype == "metric":
            # Metric expects data spread into props: {value, label, trend}
            if not isinstance(data, dict) or not data.get("value"):
                logger.warning("Dropping metric %r: missing value", title)
                continue
            rw["data"] = data

        elif wtype == "chart":
            # Chart expects data = [{label, value}] with numeric values
            if not isinstance(data, list) or len(data) == 0:
                logger.warning("Dropping chart %r: empty data", title)
                continue
            cleaned = []
            for pt in data:
                if isinstance(pt, dict) and pt.get("label") and pt.get("value") is not None:
                    try:
                        cleaned.append({"label": pt["label"], "value": float(pt["value"])})
                    except (ValueError, TypeError):
                        pass
            if len(cleaned) < 2:
                logger.warning("Dropping chart %r: <2 valid points", title)
                continue
            rw["data"] = cleaned

        elif wtype == "table":
            # Table component expects:
            #   props.columns = [{key: "Name", label: "Name"}, ...]
            #   props.data    = [{Name: "Alice", Role: "CEO"}, ...]
            if not isinstance(data, dict):
                logger.warning("Dropping table %r: data not object", title)
                continue
            cols = data.get("columns", [])
            rows = data.get("data", [])
            if not cols or not rows:
                logger.warning("Dropping table %r: empty columns/rows", title)
                continue
            rw["props"]["columns"] = [{"key": c, "label": c} for c in cols]
            rw["data"] = [
                {cols[ci]: cell for ci, cell in enumerate(row) if ci < len(cols)}
                for row in rows
                if isinstance(row, list)
            ]

        elif wtype == "feed":
            # Feed expects data = [{text, time?, type?}] (flat array, not wrapped)
            if isinstance(data, dict):
                items = data.get("items", [])
            elif isinstance(data, list):
                items = data
            else:
                logger.warning("Dropping feed %r: bad data shape", title)
                continue
            items = [it for it in items if isinstance(it, dict) and it.get("text")]
            if not items:
                logger.warning("Dropping feed %r: no items", title)
                continue
            rw["data"] = items

        elif wtype == "text":
            # Text expects data = "string"
            if isinstance(data, dict) and "content" in data:
                rw["data"] = str(data["content"])
            else:
                rw["data"] = str(data) if data else ""

        elif wtype == "terminal":
            # Terminal expects data = [{text, type?, timestamp?}]
            if isinstance(data, dict) and "lines" in data:
                rw["data"] = data["lines"]
            else:
                rw["data"] = data

        else:
            rw["data"] = data

        widgets.append(rw)

    if not widgets:
        logger.warning("Pocket %r: no valid widgets", name)
        return None

    # Build the complete Ripple UniversalSpec v2.0
    return {
        "version": "2.0",
        "intent": "dashboard",
        "lifecycle": {"type": "persistent", "id": pocket_id},
        "title": name,
        "name": name,
        "description": spec.get("description", ""),
        "category": spec.get("category") or meta.get("category", "custom"),
        "color": color,
        "logo": spec.get("logo") or meta.get("logo"),
        "display": {"columns": spec.get("columns", 3)},
        "widgets": widgets,
        "dashboard_layout": {
            "type": "masonry",
            "columns": spec.get("columns", 3),
            "gap": 10,
        },
        "metadata": {
            "category": spec.get("category") or meta.get("category", "custom"),
            "color": color,
            "logo": spec.get("logo") or meta.get("logo"),
        },
    }


@router.post("/pockets/chat")
async def pocket_chat_stream(body: ChatRequest):
    """Chat with pocket context — extracts pocket specs."""
    from pocketpaw.api.v1.chat import _APISessionBridge
    from pocketpaw.bus import get_message_bus
    from pocketpaw.bus.events import Channel, InboundMessage

    chat_id = _extract_chat_id(body.session_id)
    safe_key = _to_safe_key(chat_id)

    augmented_content = _POCKET_SYSTEM_CONTEXT + body.content

    msg = InboundMessage(
        channel=Channel.WEBSOCKET,
        sender_id="api_client",
        chat_id=chat_id,
        content=augmented_content,
        media=body.media,
        metadata={"source": "pocket_chat"},
    )
    bus = get_message_bus()
    await bus.publish_inbound(msg)

    bridge = _APISessionBridge(chat_id)
    await bridge.start()

    pocket_emitted = False

    async def _event_generator():
        nonlocal pocket_emitted
        try:
            yield (f"event: stream_start\ndata: {json.dumps({'session_id': safe_key})}\n\n")
            while True:
                try:
                    event = await asyncio.wait_for(bridge.queue.get(), timeout=1.0)
                except TimeoutError:
                    continue

                etype = event["event"]
                edata = event["data"]

                # Check tool_start for create_pocket Bash commands
                if etype == "tool_start" and not pocket_emitted:
                    cmd = ""
                    inp = edata.get("input", {})
                    if isinstance(inp, dict):
                        cmd = inp.get("command", "")
                    elif isinstance(inp, str):
                        cmd = inp

                    if "create_pocket" in cmd:
                        spec = _try_extract_pocket_from_bash(cmd)
                        spec = _prepare_pocket_spec(spec) if spec else None
                        if spec:
                            pocket_emitted = True
                            logger.info(
                                "Pocket extracted from tool_start: %s (%d widgets)",
                                spec.get("title", spec.get("name", "?")),
                                len(spec.get("widgets", [])),
                            )
                            yield (f"event: pocket_created\ndata: {json.dumps(spec)}\n\n")

                # Check tool_result for pocket-spec markers (UniversalSpec)
                if etype == "tool_result" and not pocket_emitted:
                    result = edata.get("result", "")
                    if isinstance(result, str):
                        m = _POCKET_SPEC_RE.search(result)
                        if m:
                            try:
                                spec = json.loads(m.group(1))
                                spec = _prepare_pocket_spec(spec)
                                if spec:
                                    pocket_emitted = True
                                    yield (f"event: pocket_created\ndata: {json.dumps(spec)}\n\n")
                            except json.JSONDecodeError:
                                pass

                # Check tool_result for pocket-mutation markers (add/remove widget)
                if etype == "tool_result":
                    result = edata.get("result", "")
                    if isinstance(result, str):
                        m = _POCKET_MUTATION_RE.search(result)
                        if m:
                            try:
                                mutation = json.loads(m.group(1))
                                yield (
                                    f"event: pocket_mutation\n"
                                    f"data: {json.dumps(mutation)}\n\n"
                                )
                            except json.JSONDecodeError:
                                pass

                # Forward original event
                yield (f"event: {etype}\ndata: {json.dumps(edata)}\n\n")

                if etype in ("stream_end", "error"):
                    break
        finally:
            await bridge.stop()

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
