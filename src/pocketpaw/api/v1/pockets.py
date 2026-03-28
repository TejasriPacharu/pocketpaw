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
1. Use web_search to research the topic FIRST.
2. Call the create_pocket tool directly with the JSON parameters.
3. NEVER create HTML files or write files to disk.

The create_pocket tool accepts these parameters and returns a Ripple UniversalSpec (v2.0):
{
  "title": "Company Analysis",
  "description": "Research overview",
  "category": "research",
  "color": "#0A84FF",
  "columns": 3,
  "widgets": [
    {
      "type": "metric",
      "title": "Revenue",
      "size": "sm",
      "data": {"value": "$10B", "label": "Revenue", "trend": "+15%"}
    },
    {
      "type": "chart",
      "title": "Revenue Over Time",
      "size": "md",
      "data": [{"label": "Q1", "value": 2400}, {"label": "Q2", "value": 3100}],
      "props": {"type": "bar", "height": 200}
    },
    {
      "type": "table",
      "title": "Key People",
      "size": "lg",
      "data": {"columns": ["Name", "Role"], "data": [["Alice", "CEO"], ["Bob", "CTO"]]}
    },
    {
      "type": "feed",
      "title": "Recent News",
      "size": "md",
      "data": {"items": [{"text": "Launched v2.0", "time": "2h ago", "type": "success"}]}
    }
  ]
}

Widget types:
- metric: single KPI. data: {value, label, trend?}
- chart: bar/line/area/pie. data: [{label, value}], props: {type, height?}
- table: data grid. data: {columns: [str], data: [[cell, ...]]}
- feed: event list. data: {items: [{text, time?, type?}]}
- terminal: log output. data: {lines: [{text, type?, timestamp?}]}, props: {title?}
- text: markdown. data: {content: "markdown string"}

Widget sizes: "sm" (1 col), "md" (2 cols), "lg" (full width)

Create 6-8 widgets with REAL data from web_search.
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
