"""
The model gateway is the sole path from any agent module to an LLM provider.
Agents call `ModelGateway.run(use_case=..., ...)`; they never construct a
provider client themselves. This is the CTO guardrail from the technical
roadmap's reference architecture diagram: "model providers are never called
directly from product modules."
"""

from .providers import get_provider_client
from .use_case_policy import get_policy


class ModelGateway:
    async def run(self, *, use_case: str, system_prompt: str, user_prompt: str) -> str:
        policy = get_policy(use_case)
        client = get_provider_client(policy.primary)
        return await client.complete(system_prompt=system_prompt, user_prompt=user_prompt)


model_gateway = ModelGateway()
