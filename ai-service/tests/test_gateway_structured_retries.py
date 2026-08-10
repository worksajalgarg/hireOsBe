import asyncio

from pydantic import BaseModel

from app.model_gateway.gateway import ModelGateway
from app.model_gateway.providers import Provider


def _run(coro):
    return asyncio.run(coro)


class _Schema(BaseModel):
    value: str


class _FailThenSucceedClient:
    """Fails complete_json on the first call, succeeds on the second —
    simulates a provider whose JSON-mode reliability is degrading but still
    recovers within the existing 2-attempts-per-tier retry."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("malformed JSON")
        return '{"value": "ok"}'


class _AlwaysSucceedsClient:
    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        return '{"value": "ok"}'


def test_structured_attempt_reports_one_retry_after_a_failed_first_try(monkeypatch) -> None:
    client = _FailThenSucceedClient()
    monkeypatch.setattr(
        "app.model_gateway.gateway.get_provider_client",
        lambda provider, model=None, max_tokens=None: client,
    )
    gateway = ModelGateway()
    parsed, retries_used = _run(
        gateway._structured_attempt(Provider.GEMINI, None, None, "sys", "user", _Schema)
    )
    assert parsed is not None
    assert parsed.value == "ok"
    assert retries_used == 1


def test_structured_attempt_reports_zero_retries_when_client_succeeds_immediately(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.model_gateway.gateway.get_provider_client",
        lambda provider, model=None, max_tokens=None: _AlwaysSucceedsClient(),
    )
    gateway = ModelGateway()
    parsed, retries_used = _run(
        gateway._structured_attempt(Provider.GEMINI, None, None, "sys", "user", _Schema)
    )
    assert parsed is not None
    assert retries_used == 0
