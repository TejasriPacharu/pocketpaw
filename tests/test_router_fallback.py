import pytest

from pocketpaw.agents.protocol import AgentEvent
from pocketpaw.agents.router import AgentRouter
from pocketpaw.config import Settings


class FailingBackend:
    """Backend that always fails."""

    @staticmethod
    def info():
        class Info:
            display_name = "Failing Backend"

        return Info()

    def __init__(self, settings):
        pass

    async def run(self, *args, **kwargs):
        raise RuntimeError("backend failure")

    async def stop(self):
        pass


class SuccessBackend:
    """Backend that always succeeds."""

    @staticmethod
    def info():
        class Info:
            display_name = "Success Backend"

        return Info()

    def __init__(self, settings):
        pass

    async def run(self, *args, **kwargs):
        yield AgentEvent(type="message", content="fallback worked")
        yield AgentEvent(type="done", content="")

    async def stop(self):
        pass


@pytest.mark.asyncio
async def test_router_fallback_success(monkeypatch):
    """Primary backend fails → fallback backend succeeds."""

    from pocketpaw.agents import registry

    monkeypatch.setitem(
        registry._BACKEND_REGISTRY,
        "failing_backend",
        ("tests.test_router_fallback", "FailingBackend"),
    )

    monkeypatch.setitem(
        registry._BACKEND_REGISTRY,
        "success_backend",
        ("tests.test_router_fallback", "SuccessBackend"),
    )

    settings = Settings(
        agent_backend="failing_backend",
        fallback_backends=["success_backend"],
    )

    router = AgentRouter(settings)

    events = []
    async for event in router.run("hello"):
        events.append(event)

    assert any(e.content == "fallback worked" for e in events)