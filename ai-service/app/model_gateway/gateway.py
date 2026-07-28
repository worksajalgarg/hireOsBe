"""
The model gateway is the sole path from any agent module to an LLM provider.
Agents call `ModelGateway.run(use_case=..., ...)`; they never construct a
provider client themselves. This is the CTO guardrail from the technical
roadmap's reference architecture diagram: "model providers are never called
directly from product modules."
"""

from app.config import get_settings

from .providers import (
    MockProviderClient,
    Provider,
    get_provider_client,
    is_llm_quota_error,
)
from .use_case_policy import get_policy


class ModelGateway:
    async def run(self, *, use_case: str, system_prompt: str, user_prompt: str) -> str:
        get_settings.cache_clear()
        settings = get_settings()
        mode = (settings.llm_mode or "mock").strip().lower()
        if mode == "mock":
            client = get_provider_client(Provider.MOCK)
        elif mode == "gemini":
            client = get_provider_client(Provider.GEMINI)
        elif mode in ("openrouter", "openai"):
            client = get_provider_client(Provider.OPENAI)
        else:
            policy = get_policy(use_case)
            client = get_provider_client(policy.primary)

        try:
            return await client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as exc:
            # Always allow process testing when paid/free APIs fail.
            allow_fallback = settings.llm_fallback_to_mock
            if mode == "mock":
                raise
            if allow_fallback and (is_llm_quota_error(exc) or mode in ("gemini", "openrouter", "openai")):
                mock = MockProviderClient(
                    fallback_reason=(
                        f"Mock extraction used because {mode} LLM failed "
                        f"({type(exc).__name__}: {str(exc)[:180]}). "
                        "Pipeline completed for process testing."
                    )
                )
                return await mock.complete(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
            raise


model_gateway = ModelGateway()
