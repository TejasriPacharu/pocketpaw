from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from pocketpaw.a2a.client import A2AClient
from pocketpaw.a2a.models import (
    A2AMessage,
    AgentCapabilities,
    AgentCard,
    Task,
    TaskSendParams,
    TaskState,
    TaskStatus,
    TextPart,
)
from pocketpaw.tools.builtin.a2a_delegate import A2ADelegateTool


@pytest.fixture
def mock_agent_card() -> AgentCard:
    return AgentCard(
        name="TestAgent",
        description="A test agent",
        url="http://localhost:8001",
        version="1.0.0",
        capabilities={
            "streaming": True,
            "push_notifications": False,
            "state_transition_history": True,
        },
        skills=[],
    )


@pytest.fixture
def mock_task() -> Task:
    return Task(
        id="test-task-123",
        session_id="test-session",
        status=TaskStatus(
            state=TaskState.COMPLETED,
            message=A2AMessage(role="agent", parts=[TextPart(text="Task completed.")]),
        ),
        history=[],
        metadata={},
    )


class TestA2AClient:
    async def test_get_agent_card_success(self, mock_agent_card):
        client = A2AClient()
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.content = mock_agent_card.model_dump_json().encode()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            result = await client.get_agent_card("http://localhost:8001")

            assert result.name == "TestAgent"
            mock_client_instance.get.assert_called_once_with(
                "http://localhost:8001/.well-known/agent.json"
            )

    async def test_send_task_success(self, mock_task):
        client = A2AClient()
        params = TaskSendParams(message=A2AMessage(role="user", parts=[TextPart(text="Do this")]))

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.content = mock_task.model_dump_json().encode()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            result = await client.send_task("http://localhost:8001", params)

            assert result.id == "test-task-123"
            assert result.status.state == TaskState.COMPLETED
            mock_client_instance.post.assert_called_once_with(
                "http://localhost:8001/a2a/tasks/send",
                json=params.model_dump(mode="json", exclude_none=True),
            )

    async def test_get_task_success(self, mock_task):
        client = A2AClient()
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.content = mock_task.model_dump_json().encode()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            result = await client.get_task("http://localhost:8001", "test-task-123")

            assert result.id == "test-task-123"
            mock_client_instance.get.assert_called_once_with(
                "http://localhost:8001/a2a/tasks/test-task-123"
            )

    async def test_cancel_task_success(self):
        client = A2AClient()
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.content = b""

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.__aenter__.return_value = mock_client_instance

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            await client.cancel_task("http://localhost:8001", "test-task-123")
            mock_client_instance.post.assert_called_once_with(
                "http://localhost:8001/a2a/tasks/test-task-123/cancel"
            )

    async def test_send_task_stream_success(self):
        client = A2AClient()
        params = TaskSendParams(message=A2AMessage(role="user", parts=[TextPart(text="Do this")]))

        mock_response = AsyncMock(spec=httpx.Response)

        async def mock_aiter_lines():
            yield 'data: {"event":"task_status_update"}'
            yield ""
            yield 'data: {"event":"task_status_update"}'

        mock_response.aiter_lines.side_effect = mock_aiter_lines

        from unittest.mock import MagicMock

        mock_stream_context = MagicMock()
        mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_context.__aexit__ = AsyncMock(return_value=None)

        mock_client_instance = AsyncMock()
        mock_client_instance.stream = MagicMock(return_value=mock_stream_context)
        mock_client_instance.__aenter__.return_value = mock_client_instance

        with patch("httpx.AsyncClient", return_value=mock_client_instance):
            events = []
            async for event in client.send_task_stream("http://localhost:8001", params):
                events.append(event)

            assert len(events) == 2
            assert events[0] == '{"event":"task_status_update"}'

            mock_client_instance.stream.assert_called_once_with(
                "POST",
                "http://localhost:8001/a2a/tasks/send/stream",
                json=params.model_dump(mode="json", exclude_none=True),
            )


class TestA2ADelegateTool:
    async def test_delegate_tool_success(self, mock_agent_card, mock_task):
        tool = A2ADelegateTool()

        with patch("pocketpaw.tools.builtin.a2a_delegate.A2AClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.get_agent_card = AsyncMock(return_value=mock_agent_card)
            mock_client.send_task = AsyncMock(return_value=mock_task)

            result = await tool.execute(agent_url="http://localhost:8001", task="Help me")

            assert "Error" not in result
            parsed = json.loads(result)
            assert parsed["agent_name"] == "TestAgent"
            assert parsed["task_id"] == "test-task-123"
            assert parsed["status"] == "completed"
            assert parsed["reply"] == "Task completed."

    async def test_delegate_tool_card_fetch_failure(self):
        tool = A2ADelegateTool()

        with patch("pocketpaw.tools.builtin.a2a_delegate.A2AClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.get_agent_card = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            result = await tool.execute(agent_url="http://localhost:8001", task="Help me")

            assert result.startswith("Error:")
            assert "Failed to fetch Agent Card" in result
            assert "Connection refused" in result

    async def test_delegate_tool_multi_turn_success(self, mock_agent_card, mock_task):
        tool = A2ADelegateTool()

        # Setup an existing task with history
        existing_task = Task(
            id="test-task-123",
            session_id="test-session",
            status=TaskStatus(state=TaskState.COMPLETED),
            history=[
                A2AMessage(role="user", parts=[TextPart(text="Hello")]),
                A2AMessage(role="agent", parts=[TextPart(text="Hi there")]),
            ],
        )

        with patch("pocketpaw.tools.builtin.a2a_delegate.A2AClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.get_agent_card = AsyncMock(return_value=mock_agent_card)
            mock_client.get_task = AsyncMock(return_value=existing_task)
            mock_client.send_task = AsyncMock(return_value=mock_task)

            result = await tool.execute(
                agent_url="http://localhost:8001", task="Help me more", task_id="test-task-123"
            )

            assert "Error" not in result
            mock_client.get_task.assert_called_once_with("http://localhost:8001", "test-task-123")

            # Verify send_task was called with the combined history
            call_args = mock_client.send_task.call_args
            sent_params = call_args[0][1]
            assert sent_params.id == "test-task-123"
            assert len(sent_params.message.parts) == 3
            assert sent_params.message.parts[0].text == "Hello"
            assert sent_params.message.parts[1].text == "Hi there"
            assert sent_params.message.parts[2].text == "Help me more"

    async def test_delegate_tool_multi_turn_unsupported(self, mock_agent_card, mock_task):
        tool = A2ADelegateTool()

        mock_agent_card.capabilities.state_transition_history = False

        with patch("pocketpaw.tools.builtin.a2a_delegate.A2AClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.get_agent_card = AsyncMock(return_value=mock_agent_card)
            mock_client.get_task = AsyncMock(return_value=mock_task)

            result = await tool.execute(
                agent_url="http://localhost:8001", task="Help me more", task_id="test-task-123"
            )

            assert result.startswith("Error:")
            assert "does not support multi-turn" in result

    async def test_delegate_tool_no_capabilities(self, mock_agent_card):
        tool = A2ADelegateTool()

        # Override card to have no capabilities
        mock_agent_card.capabilities = AgentCapabilities(
            streaming=False,
            push_notifications=False,
            state_transition_history=False,
        )
        mock_agent_card.skills = []

        with patch("pocketpaw.tools.builtin.a2a_delegate.A2AClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.get_agent_card = AsyncMock(return_value=mock_agent_card)

            result = await tool.execute(agent_url="http://localhost:8001", task="Help me")

            assert result.startswith("Error:")
            assert "advertises no usable capabilities" in result

    async def test_delegate_tool_task_send_failure(self, mock_agent_card):
        tool = A2ADelegateTool()

        with patch("pocketpaw.tools.builtin.a2a_delegate.A2AClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.get_agent_card = AsyncMock(return_value=mock_agent_card)
            mock_client.send_task = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

            result = await tool.execute(agent_url="http://localhost:8001", task="Help me")

            assert result.startswith("Error:")
            assert "Failed to submit task" in result
            assert "Timeout" in result
