"""Gateway routing for LLM_MODE=local (no real model load)."""

from __future__ import annotations

import asyncio

import pytest

from app.config import get_settings
from app.model_gateway.gateway import ModelGateway
from app.model_gateway.providers import (
    LocalTransformersProviderClient,
    Provider,
    get_provider_client,
)


def test_gateway_selects_local_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_MODE", "local")
    monkeypatch.setenv("LLM_FALLBACK_TO_MOCK", "false")
    get_settings.cache_clear()

    captured: dict[str, str] = {}

    async def fake_complete(self, *, system_prompt: str, user_prompt: str) -> str:
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        return (
            '{"contact":{"full_name":"Ada","email":null,"phone":null,'
            '"location":null,"linkedin":null,"website":null},"summary":null,'
            '"experience":[],"education":[],"skills":[],"certifications":[],'
            '"languages":[]}'
        )

    monkeypatch.setattr(LocalTransformersProviderClient, "complete", fake_complete)

    async def _run() -> str:
        gateway = ModelGateway()
        return await gateway.run(
            use_case="resume_parsing",
            system_prompt="sys",
            user_prompt="user resume text",
        )

    raw = asyncio.run(_run())

    assert '"full_name":"Ada"' in raw
    assert captured["system"] == "sys"
    assert captured["user"] == "user resume text"

    client = get_provider_client(Provider.LOCAL)
    assert isinstance(client, LocalTransformersProviderClient)

    get_settings.cache_clear()
