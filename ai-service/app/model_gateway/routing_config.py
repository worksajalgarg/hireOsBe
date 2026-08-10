"""Loads USE_CASE_POLICIES from a YAML file instead of a hardcoded Python
dict literal — see config/model_routing.yaml and
docs/adr/0005-config-driven-model-routing.md for why. Kept in model_gateway/
(not voice_agent/) since it populates a model_gateway module-level dict used
by every use case, not just the voice/discovery ones.

Deliberately does not import any provider SDK — only `Provider` (an enum,
not a client) — so this file has no bearing on
tests/test_model_gateway_boundary.py's guardrail.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .providers import Provider
from .use_case_policy import ProviderChoice, UseCasePolicy

# Every use case any caller in the codebase actually references (gateway_llm.py,
# discovery_llm.py, and the non-voice agent routers) — checked against the
# loaded file so a use case accidentally dropped from YAML fails at startup,
# not at the first get_policy() call mid-interview.
REQUIRED_USE_CASES = (
    "role_intake_scorecard",
    "resume_parsing",
    "evidence_matching",
    "interview_evaluation",
    "candidate_report",
    "voice_interview_turn",
    "voice_interview_summary",
    "role_discovery_turn",
    "role_discovery_extraction",
)


class RoutingConfigError(RuntimeError):
    pass


class ChainEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    # First-chunk timeout override for this tier — see ProviderChoice.timeout_s
    # and gateway.py's _FIRST_CHUNK_TIMEOUT_S default. No max_tokens override
    # exists yet: ProviderChoice/providers.py don't support one today (see
    # _OpenAICompatibleClient's hardcoded default) — adding that is a
    # separate, larger change to providers.py, out of scope for this
    # behavior-preserving migration.
    timeout_s: float | None = None

    @field_validator("provider")
    @classmethod
    def _valid_provider(cls, value: str) -> str:
        valid = {p.value for p in Provider}
        if value not in valid:
            raise ValueError(f"unknown provider '{value}' — valid: {', '.join(sorted(valid))}")
        return value

    @field_validator("timeout_s")
    @classmethod
    def _positive_timeout(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError(f"timeout_s must be > 0, got {value}")
        return value


class UseCasePolicyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chain: list[ChainEntry]
    rationale: str

    @field_validator("chain")
    @classmethod
    def _non_empty_chain(cls, value: list[ChainEntry]) -> list[ChainEntry]:
        if not value:
            raise ValueError("chain must have at least one entry")
        seen: set[tuple[str, str]] = set()
        for entry in value:
            key = (entry.provider, entry.model)
            if key in seen:
                raise ValueError(f"duplicate (provider, model) in chain: {key}")
            seen.add(key)
        return value


class RoutingConfigFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_cases: dict[str, UseCasePolicyEntry]

    @model_validator(mode="after")
    def _all_required_present(self) -> "RoutingConfigFile":
        missing = [uc for uc in REQUIRED_USE_CASES if uc not in self.use_cases]
        if missing:
            raise ValueError(f"routing config is missing required use case(s): {missing}")
        return self


def load_routing_config(path: Path) -> dict[str, UseCasePolicy]:
    """Reads and validates `path` (see config/model_routing.yaml), returning
    a dict ready to populate use_case_policy.USE_CASE_POLICIES. Raises
    RoutingConfigError with a clear message on any malformed/incomplete
    config — this must fail at startup, not mid-call."""
    try:
        raw_text = path.read_text()
    except OSError as exc:
        raise RoutingConfigError(f"Could not read routing config at {path}: {exc}") from exc

    try:
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise RoutingConfigError(f"Routing config at {path} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise RoutingConfigError(f"Routing config at {path} must be a mapping of use cases")

    try:
        parsed = RoutingConfigFile(use_cases=raw)
    except Exception as exc:
        raise RoutingConfigError(f"Routing config at {path} is invalid: {exc}") from exc

    policies: dict[str, UseCasePolicy] = {}
    for use_case, entry in parsed.use_cases.items():
        policies[use_case] = UseCasePolicy(
            chain=[
                ProviderChoice(
                    provider=Provider(choice.provider),
                    model=choice.model,
                    timeout_s=choice.timeout_s,
                )
                for choice in entry.chain
            ],
            rationale=entry.rationale,
        )
    return policies
