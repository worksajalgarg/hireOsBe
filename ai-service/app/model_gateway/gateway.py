"""
The model gateway is the sole path from any agent module to an LLM provider.
Agents call `ModelGateway.run(use_case=..., ...)`; they never construct a
provider client themselves. This is the CTO guardrail from the technical
roadmap's reference architecture diagram: "model providers are never called
directly from product modules."
"""

from dataclasses import dataclass

from app.config import get_settings

from .providers import (
    MockProviderClient,
    Provider,
    get_provider_client,
    is_llm_quota_error,
)
from .use_case_policy import get_policy


class ModelGateway:
    async def run_detailed(
        self, *, use_case: str, system_prompt: str, user_prompt: str
    ) -> "GatewayResult":
        """Run a completion and retain auditable provider/fallback information."""
        get_settings.cache_clear()
        settings = get_settings()
        mode = (settings.llm_mode or "mock").strip().lower()
        if mode == "mock":
            client = get_provider_client(Provider.MOCK)
        elif mode == "local":
            client = get_provider_client(Provider.LOCAL)
        elif mode == "gemini":
            client = get_provider_client(Provider.GEMINI)
        elif mode in ("openrouter", "openai"):
            client = get_provider_client(Provider.OPENAI)
        else:
            policy = get_policy(use_case)
            client = get_provider_client(policy.primary)

        try:
            content = await client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            return GatewayResult(
                content=content,
                provider=client.provider.value,
                model_name=_model_name(settings, mode),
                fallback_used=False,
            )
        except Exception as exc:
            allow_fallback = settings.llm_fallback_to_mock
            if mode == "mock":
                raise
            if allow_fallback and (
                is_llm_quota_error(exc)
                or mode in ("gemini", "openrouter", "openai", "local")
            ):
                mock = MockProviderClient(
                    fallback_reason=(
                        f"Mock extraction used because {mode} LLM failed "
                        f"({type(exc).__name__}: {str(exc)[:180]}). "
                        "Pipeline completed for process testing."
                    )
                )
                content = await mock.complete(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                return GatewayResult(
                    content=content,
                    provider=mock.provider.value,
                    model_name="mock",
                    fallback_used=True,
                )
            raise

    async def run(self, *, use_case: str, system_prompt: str, user_prompt: str) -> str:
        result = await self.run_detailed(
            use_case=use_case,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return result.content


@dataclass(frozen=True)
class GatewayResult:
    content: str
    provider: str
    model_name: str
    fallback_used: bool


def _model_name(settings, mode: str) -> str:
    if mode == "local":
        return settings.local_llm_model
    if mode == "gemini":
        return settings.gemini_model
    if mode in ("openrouter", "openai"):
        return settings.openai_model
    return mode


model_gateway = ModelGateway()
