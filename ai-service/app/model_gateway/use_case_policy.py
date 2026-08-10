"""
Per-use-case model routing policy, matching the PRD's "AI model strategy by
module" table. Kept as a plain data structure (not hidden in agent code) so
routing decisions are auditable and changeable without touching agent logic.

Each policy is an ordered chain: gateway.py tries providers in list order,
falling through to the next on any failure (including a too-slow first
chunk — see gateway.py's _FIRST_CHUNK_TIMEOUT_S) until one succeeds or the
chain is exhausted. Single-entry chains have no fallback at all.

USE_CASE_POLICIES itself is populated at startup from
config/model_routing.yaml (see routing_config.py's load_routing_config(),
called once from voice_agent/worker.py's main() and app/main.py's startup
hook) — the YAML file, not this module, is the auditable source of truth for
which provider/model/timeout each use case's chain uses. See
docs/adr/0005-config-driven-model-routing.md for why this replaced a
hardcoded dict literal here. This module still owns the dataclasses,
get_policy() lookup, and the apply_provider_priority() reordering primitive
— only the population of USE_CASE_POLICIES moved out of Python source.

Provider tiering (no working OpenAI key at present — Gemini/Groq/OpenRouter
are the live providers):
- small/high-volume, low-reasoning work -> Groq's small model (fastest, cheapest)
- medium reasoning / synthesis          -> Groq's larger model or Gemini flash
- large/complex reasoning               -> OpenRouter routed to a frontier
  model (Claude Sonnet 5) — the only path to top-tier reasoning quality
  without an OpenAI key
- realtime voice turn generation        -> see config/model_routing.yaml's
  voice_interview_turn/voice_interview_summary/role_discovery_* entries for
  the current live-tested ordering, which has shifted from pure
  latency-optimization (Groq first) to prioritizing a free-tier OpenRouter
  model first, after repeatedly exhausting Groq's daily token cap and
  Gemini's per-minute cap simultaneously during heavy dev testing (see each
  entry's rationale in the YAML).
"""

from dataclasses import dataclass

from .providers import Provider


@dataclass(frozen=True)
class ProviderChoice:
    provider: Provider
    model: str | None
    # First-chunk timeout for this specific tier (see gateway.py's
    # _FIRST_CHUNK_TIMEOUT_S default) — None means "use the default."
    # Needed because tiers have genuinely different latency profiles: a free
    # OpenRouter model's TTFT was live-observed ranging 0.78s-4.27s across
    # six calls a second apart (shared/lower-priority free pool), while
    # Groq's paid tier is tightly 0.3-1.3s. One global timeout tuned for
    # Groq was killing perfectly-fine free-tier calls that just needed a
    # bit more patience, forcing spurious fallbacks on nearly every turn.
    timeout_s: float | None = None
    # Output token budget for this tier's structured calls — None means "use
    # the client's default" (_OpenAICompatibleClient's 2048). Needed because
    # a large evidence-grounded schema (many claim lists, each carrying a
    # verbatim source_text) on a long document can need well more than 2048
    # output tokens; confirmed in practice — a real ~4700-char resume with
    # 4 jobs truncated Groq's response, silently leaving education/projects/
    # awards empty rather than failing outright (they're the fields the
    # schema declares last, after work_history/skills).
    max_tokens: int | None = None


@dataclass(frozen=True)
class UseCasePolicy:
    chain: list[ProviderChoice]
    rationale: str

    @property
    def primary(self) -> ProviderChoice:
        return self.chain[0]


# Final ranking deliberately has no entry here: PRD Section 7.2 / roadmap
# Section 5 — final ranking uses no LLM at all, only deterministic scoring.
#
# Populated at startup by routing_config.load_routing_config() (see
# voice_agent/worker.py's main() and app/main.py's startup hook) from
# config/model_routing.yaml — empty until that call runs. Tests populate it
# via tests/conftest.py's autouse fixture.
USE_CASE_POLICIES: dict[str, UseCasePolicy] = {}


def get_policy(use_case: str) -> UseCasePolicy:
    if use_case not in USE_CASE_POLICIES:
        raise KeyError(f"No routing policy defined for use case '{use_case}'")
    return USE_CASE_POLICIES[use_case]


def _reorder_chain(chain: list[ProviderChoice], order: list[Provider]) -> list[ProviderChoice]:
    """Providers named in `order` come first, in that order; any tier not
    mentioned keeps its original relative position, appended after. Never
    adds or removes a tier — only changes which one runs first."""
    priority = {provider: i for i, provider in enumerate(order)}
    indexed = list(enumerate(chain))
    indexed.sort(key=lambda pair: (priority.get(pair[1].provider, len(order) + pair[0]), pair[0]))
    return [choice for _, choice in indexed]


def apply_provider_priority(use_cases: list[str], order: list[Provider]) -> None:
    """Reorders the chain for each named use case to try providers in
    `order` first — called once at worker startup (see voice_agent/worker.py)
    from a runtime setting (voice_agent/config.py's llm_provider_priority),
    so which tier runs first can change via an env var instead of editing
    this file's hardcoded chains directly. Never changes *which*
    providers/models are available for a use case (that stays defined once,
    above — the auditable source of truth this module's docstring already
    describes) — only the order they're tried in."""
    for use_case in use_cases:
        policy = get_policy(use_case)
        USE_CASE_POLICIES[use_case] = UseCasePolicy(
            chain=_reorder_chain(policy.chain, order),
            rationale=policy.rationale,
        )
