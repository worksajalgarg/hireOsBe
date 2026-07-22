"""
Provider client construction is isolated to this module. Nothing outside
model_gateway/ may import an LLM provider SDK (openai, anthropic,
google-generativeai, ...) directly — see docs/adr/0002-model-gateway-boundary.md.

No provider SDKs are wired up yet in this Sprint-1 scaffold; each provider
is a stub that raises until a real client is added in Sprint 2+.
"""

from enum import Enum


class Provider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class ProviderClient:
    def __init__(self, provider: Provider):
        self.provider = provider

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError(
            f"Provider '{self.provider.value}' is not wired up yet — "
            "Sprint 1 scaffold only defines the gateway boundary."
        )


def get_provider_client(provider: Provider) -> ProviderClient:
    return ProviderClient(provider)
