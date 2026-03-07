import json
from typing import Any

from pocketpaw.a2a.client import A2AClient
from pocketpaw.a2a.models import A2AMessage, TaskSendParams, TextPart
from pocketpaw.tools.protocol import BaseTool


class A2ADelegateTool(BaseTool):
    """Tool for delegating tasks to external A2A-compatible agents."""

    @property
    def name(self) -> str:
        return "delegate_to_a2a_agent"

    @property
    def description(self) -> str:
        return (
            "Delegates a task to an external A2A-compatible agent on the network. "
            "Provide the base URL of the agent and a clear description of the task. "
            "Note: This tool blocks while waiting for the remote agent to complete "
            "the task (up to a 120-second timeout)."
        )

    @property
    def trust_level(self) -> str:
        return "standard"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_url": {
                    "type": "string",
                    "description": "The base URL of the external A2A agent (e.g., 'http://localhost:8001').",
                },
                "task": {
                    "type": "string",
                    "description": "The complete instructions or query for the external agent.",
                },
                "task_id": {
                    "type": "string",
                    "description": (
                        "Optional. The ID of an existing A2A task to continue "
                        "a multi-turn conversation."
                    ),
                },
            },
            "required": ["agent_url", "task"],
        }

    async def execute(self, agent_url: str, task: str, task_id: str | None = None) -> str:
        client = A2AClient()

        try:
            # 1. Discover capabilities
            card = await client.get_agent_card(agent_url)
        except Exception as e:
            return self._error(
                f"Failed to fetch Agent Card from {agent_url}: {e}\n"
                f"Ensure the agent is running and supports A2A."
            )

        # Ensure the remote agent advertises at least some capability
        if not card.capabilities.streaming and not card.skills:
            return self._error(f"Agent at {agent_url} advertises no usable capabilities/skills.")

        # 2. Support multi-turn by fetching history if task_id provided
        history_parts = []
        if task_id:
            try:
                existing_task = await client.get_task(agent_url, task_id)
                # Ensure the external agent actually supports state transitions
                if not card.capabilities.state_transition_history:
                    return self._error(
                        f"Agent at {agent_url} does not support multi-turn task history."
                    )

                # A2A protocol: to continue a task, send the full history in the message
                # For simplicity here we assume the new message just appends to what was discussed
                for msg in existing_task.history:
                    history_parts.extend(msg.parts)
            except Exception as e:
                return self._error(
                    f"Failed to retrieve existing task {task_id} from {agent_url}: {e}"
                )

        # 3. Formulate task parameters
        parts = history_parts + [TextPart(text=task)]

        # If continuing, we MUST send the same task_id
        send_kwargs = {"message": A2AMessage(role="user", parts=parts)}
        if task_id:
            send_kwargs["id"] = task_id

        params = TaskSendParams(**send_kwargs)

        try:
            # 4. Submit task (blocking send for now)
            result_task = await client.send_task(agent_url, params)
        except Exception as e:
            return self._error(f"Failed to submit task to {agent_url}: {e}")

        # Extract final response message
        if not result_task.status.message or not result_task.status.message.parts:
            return self._error("Agent returned no content.")

        agent_reply = " ".join(
            part.text for part in result_task.status.message.parts if part.type == "text"
        )

        status_state = result_task.status.state.value

        return self._success(
            json.dumps(
                {
                    "agent_name": card.name,
                    "task_id": result_task.id,
                    "status": status_state,
                    "reply": agent_reply,
                },
                indent=2,
            )
        )
