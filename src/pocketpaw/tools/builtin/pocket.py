# Pocket tools — CreatePocketTool, AddWidgetTool, RemoveWidgetTool.
# Updated: output Ripple UniversalSpec (v2.0) with intent='dashboard'
# instead of legacy custom pocket JSON format.
# AddWidgetTool and RemoveWidgetTool added for widget-level mutations.

import json
import logging
from datetime import UTC, datetime
from typing import Any

from pocketpaw.tools.protocol import BaseTool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Widget type mapping: old display.type -> Ripple widget type
# ---------------------------------------------------------------------------
_DISPLAY_TYPE_TO_RIPPLE = {
    "stats": "metric",
    "chart": "chart",
    "table": "table",
    "activity": "feed",
    "feed": "feed",
    "metric": "metric",
    "terminal": "terminal",
}

# Map old col-span to Ripple size
_SPAN_TO_SIZE = {
    "col-span-1": "sm",
    "col-span-2": "md",
    "col-span-3": "lg",
}


def _convert_legacy_widget(widget: dict[str, Any], widget_id: str) -> list[dict[str, Any]]:
    """Convert a legacy widget dict to one or more Ripple widget dicts.

    A stats widget with multiple stats becomes multiple metric widgets.
    Everything else maps 1:1.
    """
    display = widget.get("display", {})
    display_type = display.get("type", "metric")
    ripple_type = _DISPLAY_TYPE_TO_RIPPLE.get(display_type, display_type)
    size = _SPAN_TO_SIZE.get(widget.get("span", "col-span-1"), "sm")
    title = widget.get("name", widget.get("title", "Widget"))

    if display_type == "stats":
        # Each stat becomes its own metric widget
        stats = display.get("stats", [])
        if not stats:
            return [{"id": widget_id, "type": "metric", "title": title, "size": size, "data": {}}]
        widgets = []
        for j, stat in enumerate(stats):
            wid = f"{widget_id}-s{j}" if len(stats) > 1 else widget_id
            widgets.append({
                "id": wid,
                "type": "metric",
                "title": stat.get("label", title),
                "size": "sm",
                "data": {
                    "value": stat.get("value", ""),
                    "label": stat.get("label", ""),
                    "trend": stat.get("trend", ""),
                },
            })
        return widgets

    if display_type == "chart":
        data = display.get("bars", display.get("data", []))
        chart_type = display.get("chartType", display.get("type", "bar"))
        if chart_type == "chart":
            chart_type = "bar"
        return [{
            "id": widget_id,
            "type": "chart",
            "title": title,
            "size": size,
            "data": [{"label": d.get("label", ""), "value": d.get("value", 0)} for d in data]
            if isinstance(data, list) else data,
            "props": {"type": chart_type, "height": 200},
        }]

    if display_type == "table":
        headers = display.get("headers", [])
        rows = display.get("rows", [])
        return [{
            "id": widget_id,
            "type": "table",
            "title": title,
            "size": size,
            "data": {
                "columns": headers,
                "data": [r.get("cells", r) if isinstance(r, dict) else r for r in rows],
            },
        }]

    if display_type in ("feed", "activity"):
        items = display.get("feedItems", display.get("items", []))
        return [{
            "id": widget_id,
            "type": "feed",
            "title": title,
            "size": size,
            "data": {"items": items},
        }]

    if display_type == "metric":
        metric = display.get("metric", {})
        return [{
            "id": widget_id,
            "type": "metric",
            "title": metric.get("label", title),
            "size": size,
            "data": {
                "value": metric.get("value", ""),
                "label": metric.get("label", ""),
                "trend": metric.get("trend", ""),
                "description": metric.get("description", ""),
            },
        }]

    if display_type == "terminal":
        return [{
            "id": widget_id,
            "type": "terminal",
            "title": display.get("termTitle", title),
            "size": size,
            "data": {"lines": display.get("termLines", display.get("lines", []))},
            "props": {
                "title": display.get("termTitle", title),
                "interactive": display.get("interactive", False),
            },
        }]

    # Fallback — pass through as-is
    return [{
        "id": widget_id,
        "type": ripple_type,
        "title": title,
        "size": size,
        "data": display,
    }]


class CreatePocketTool(BaseTool):
    """Create a pocket workspace that outputs a Ripple UniversalSpec.

    The agent calls this tool after gathering information via web_search,
    browser, or other research tools. The tool returns a UniversalSpec
    JSON (v2.0, intent=dashboard) that the frontend renders with
    <Ripple spec={...} />.
    """

    @property
    def name(self) -> str:
        return "create_pocket"

    @property
    def description(self) -> str:
        return (
            "Create a pocket workspace as a Ripple UniversalSpec (v2.0). "
            "Call this after researching a topic. "
            "Provide a title, description, category, and a list of widgets.\n\n"
            "Widget types:\n"
            "- metric: single KPI. data: {value, label, trend?}\n"
            "- chart: bar/line/area/pie. data: [{label, value}], "
            "props: {type: 'bar'|'line'|'area'|'pie', height?: 200}\n"
            "- table: data table. data: {columns: [str], data: [[...]]}\n"
            "- feed: activity feed. data: {items: [{text, time?, type?}]}\n"
            "- terminal: log output. data: {lines: [{text, type?, timestamp?}]}, "
            "props: {title?, interactive?}\n"
            "- text: markdown block. data: {content: 'markdown string'}\n\n"
            "Widget sizes: 'sm' (1 col), 'md' (2 cols), 'lg' (3 cols / full width).\n\n"
            "Colors: #30D158 (green), #FF453A (red), #FF9F0A (orange), "
            "#0A84FF (blue), #BF5AF2 (purple), #5E5CE6 (indigo)."
        )

    @property
    def trust_level(self) -> str:
        return "standard"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Pocket title (e.g. 'Vercel Analysis')",
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of the pocket's purpose",
                },
                "category": {
                    "type": "string",
                    "description": "Category: research, business, data, mission, deep-work, custom",
                    "enum": [
                        "research",
                        "business",
                        "data",
                        "mission",
                        "deep-work",
                        "custom",
                        "hospitality",
                    ],
                },
                "color": {
                    "type": "string",
                    "description": "Accent color for the pocket (hex, e.g. '#0A84FF')",
                },
                "columns": {
                    "type": "integer",
                    "description": "Grid columns (default 3)",
                },
                "widgets": {
                    "type": "array",
                    "description": "List of Ripple widgets",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "description": "Widget type: metric, chart, table, "
                            "feed, terminal, text",
                                "enum": ["metric", "chart", "table", "feed", "terminal", "text"],
                            },
                            "title": {
                                "type": "string",
                                "description": "Widget title",
                            },
                            "size": {
                                "type": "string",
                                "description": "Widget size: sm, md, lg",
                                "enum": ["sm", "md", "lg"],
                            },
                            "data": {
                                "type": "object",
                                "description": "Widget data (shape depends on type)",
                            },
                            "props": {
                                "type": "object",
                                "description": "Optional rendering props (e.g. chart type, height)",
                            },
                        },
                        "required": ["type", "title", "data"],
                    },
                },
            },
            "required": ["title", "description", "category", "widgets"],
        }

    async def execute(
        self,
        title: str = "",
        description: str = "",
        category: str = "research",
        widgets: list[dict[str, Any]] | None = None,
        color: str = "#0A84FF",
        columns: int = 3,
        # Legacy parameter names (backward compat)
        name: str = "",
        **kwargs: Any,
    ) -> str:
        """Build and return a Ripple UniversalSpec as JSON."""
        import uuid

        pocket_id = f"ai-{uuid.uuid4().hex[:8]}"
        # Support legacy 'name' param
        pocket_title = title or name or "Untitled Pocket"
        widgets = widgets or []

        # Build widget list with IDs
        built_widgets: list[dict[str, Any]] = []
        for i, w in enumerate(widgets):
            wid = f"{pocket_id}-w{i}"

            # If widget already has Ripple 'type' field, use it directly
            if "type" in w and w["type"] in (
                "metric", "chart", "table", "feed", "terminal", "text",
            ):
                widget = {
                    "id": w.get("id", wid),
                    "type": w["type"],
                    "title": w.get("title", f"Widget {i + 1}"),
                    "size": w.get("size", "sm"),
                    "data": w.get("data", {}),
                }
                if w.get("props"):
                    widget["props"] = w["props"]
                built_widgets.append(widget)
            elif "display" in w:
                # Legacy format — convert
                converted = _convert_legacy_widget(w, wid)
                built_widgets.extend(converted)
            else:
                # Minimal widget
                built_widgets.append({
                    "id": wid,
                    "type": w.get("type", "text"),
                    "title": w.get("title", w.get("name", f"Widget {i + 1}")),
                    "size": w.get("size", "sm"),
                    "data": w.get("data", {}),
                })

        spec = {
            "version": "2.0",
            "intent": "dashboard",
            "lifecycle": {"type": "persistent", "id": pocket_id},
            "title": pocket_title,
            "description": description,
            "display": {"columns": columns},
            "widgets": built_widgets,
            "dashboard_layout": {"type": "grid", "columns": columns, "gap": 10},
            "metadata": {
                "category": category,
                "color": color,
                "created_at": datetime.now(UTC).isoformat(),
                "pocket_version": "2.0",
            },
        }

        result_json = json.dumps(spec, indent=2)

        # Use a marker so the frontend can detect this is a pocket spec
        marker = f"<!-- pocket-spec:{result_json}:pocket-spec -->"
        msg = f"Created pocket **{pocket_title}** with {len(built_widgets)} widgets."
        return f"{marker}\n\n{msg}"


class AddWidgetTool(BaseTool):
    """Add a widget to an existing pocket spec."""

    @property
    def name(self) -> str:
        return "add_widget"

    @property
    def description(self) -> str:
        return (
            "Add a widget to an existing pocket. Provide the pocket_id and the widget spec. "
            "Returns a mutation instruction the frontend applies to the live spec."
        )

    @property
    def trust_level(self) -> str:
        return "standard"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pocket_id": {
                    "type": "string",
                    "description": "ID of the pocket to add the widget to",
                },
                "widget": {
                    "type": "object",
                    "description": "Widget spec: {type, title, size?, data, props?}",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["metric", "chart", "table", "feed", "terminal", "text"],
                        },
                        "title": {"type": "string"},
                        "size": {"type": "string", "enum": ["sm", "md", "lg"]},
                        "data": {"type": "object"},
                        "props": {"type": "object"},
                    },
                    "required": ["type", "title", "data"],
                },
                "position": {
                    "type": "integer",
                    "description": "Insert position (0-indexed). Omit to append at end.",
                },
            },
            "required": ["pocket_id", "widget"],
        }

    async def execute(
        self,
        pocket_id: str,
        widget: dict[str, Any],
        position: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Return a mutation instruction for adding a widget."""
        import uuid

        widget_id = widget.get("id", f"{pocket_id}-w{uuid.uuid4().hex[:6]}")
        built_widget = {
            "id": widget_id,
            "type": widget.get("type", "text"),
            "title": widget.get("title", "New Widget"),
            "size": widget.get("size", "sm"),
            "data": widget.get("data", {}),
        }
        if widget.get("props"):
            built_widget["props"] = widget["props"]

        mutation = {
            "action": "add_widget",
            "pocket_id": pocket_id,
            "widget": built_widget,
        }
        if position is not None:
            mutation["position"] = position

        result_json = json.dumps(mutation, indent=2)
        marker = f"<!-- pocket-mutation:{result_json}:pocket-mutation -->"
        msg = f"Added widget **{built_widget['title']}** to pocket `{pocket_id}`."
        return f"{marker}\n\n{msg}"


class RemoveWidgetTool(BaseTool):
    """Remove a widget from an existing pocket spec."""

    @property
    def name(self) -> str:
        return "remove_widget"

    @property
    def description(self) -> str:
        return (
            "Remove a widget from an existing pocket by widget ID. "
            "Returns a mutation instruction the frontend applies."
        )

    @property
    def trust_level(self) -> str:
        return "standard"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pocket_id": {
                    "type": "string",
                    "description": "ID of the pocket",
                },
                "widget_id": {
                    "type": "string",
                    "description": "ID of the widget to remove",
                },
            },
            "required": ["pocket_id", "widget_id"],
        }

    async def execute(
        self,
        pocket_id: str,
        widget_id: str,
        **kwargs: Any,
    ) -> str:
        """Return a mutation instruction for removing a widget."""
        mutation = {
            "action": "remove_widget",
            "pocket_id": pocket_id,
            "widget_id": widget_id,
        }

        result_json = json.dumps(mutation, indent=2)
        marker = f"<!-- pocket-mutation:{result_json}:pocket-mutation -->"
        msg = f"Removed widget `{widget_id}` from pocket `{pocket_id}`."
        return f"{marker}\n\n{msg}"
