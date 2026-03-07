import typing

import httpx

from pocketpaw.a2a.models import AgentCard, Task, TaskSendParams


def _handle_response(response: httpx.Response) -> bytes:
    """Check for errors and return the raw response bytes."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"A2A remote agent error {e.response.status_code}: {e.response.text}"
        ) from e
    return response.content


class A2AClient:
    """Asynchronous client for interacting with external A2A agents."""

    def __init__(self, timeout: float = 120.0):
        self.timeout = timeout

    async def get_agent_card(self, base_url: str) -> AgentCard:
        """Fetch the Agent Card capabilities manifest from a remote agent."""
        url = f"{base_url.rstrip('/')}/.well-known/agent.json"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            content = _handle_response(response)
            return AgentCard.model_validate_json(content)

    async def send_task(self, base_url: str, params: TaskSendParams) -> Task:
        """Submit a task to a remote A2A agent (blocking response)."""
        url = f"{base_url.rstrip('/')}/a2a/tasks/send"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url, json=params.model_dump(mode="json", exclude_none=True)
            )
            content = _handle_response(response)
            return Task.model_validate_json(content)

    async def send_task_stream(
        self, base_url: str, params: TaskSendParams
    ) -> typing.AsyncGenerator[str, None]:
        """Submit a task and yield SSE events from a remote A2A agent."""
        url = f"{base_url.rstrip('/')}/a2a/tasks/send/stream"
        payload = params.model_dump(mode="json", exclude_none=True)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=payload) as response:
                _handle_response(response)
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        yield line[5:].strip()

    async def get_task(self, base_url: str, task_id: str) -> Task:
        """Poll the current status of a previously submitted task."""
        url = f"{base_url.rstrip('/')}/a2a/tasks/{task_id}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            content = _handle_response(response)
            return Task.model_validate_json(content)

    async def cancel_task(self, base_url: str, task_id: str) -> None:
        """Request cancellation of an in-flight task."""
        url = f"{base_url.rstrip('/')}/a2a/tasks/{task_id}/cancel"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url)
            _handle_response(response)
