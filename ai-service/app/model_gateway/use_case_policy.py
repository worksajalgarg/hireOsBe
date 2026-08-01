"""
Per-use-case model routing policy, matching the PRD's "AI model strategy by
module" table. Kept as a plain data structure (not hidden in agent code) so
routing decisions are auditable and changeable without touching agent logic.

Each policy is an ordered chain: gateway.py tries providers in list order,
falling through to the next on any failure (including a too-slow first
chunk — see gateway.py's _FIRST_CHUNK_TIMEOUT_S) until one succeeds or the
chain is exhausted. Single-entry chains have no fallback at all.

Provider tiering (no working OpenAI key at present — Gemini/Groq/OpenRouter
are the live providers):
- small/high-volume, low-reasoning work -> Groq's small model (fastest, cheapest)
- medium reasoning / synthesis          -> Groq's larger model or Gemini flash
- large/complex reasoning               -> OpenRouter routed to a frontier
  model (Claude Sonnet 5) — the only path to top-tier reasoning quality
  without an OpenAI key
- realtime voice turn generation        -> see the voice_interview_turn/
  voice_interview_summary/role_discovery_* entries below for the current
  live-tested ordering, which has shifted from pure latency-optimization
  (Groq first) to prioritizing a free-tier OpenRouter model first, after
  repeatedly exhausting Groq's daily token cap and Gemini's per-minute cap
  simultaneously during heavy dev testing (see each entry's rationale).
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


@dataclass(frozen=True)
class UseCasePolicy:
    chain: list[ProviderChoice]
    rationale: str

    @property
    def primary(self) -> ProviderChoice:
        return self.chain[0]


# Final ranking deliberately has no entry here: PRD Section 7.2 / roadmap
# Section 5 — final ranking uses no LLM at all, only deterministic scoring.
USE_CASE_POLICIES: dict[str, UseCasePolicy] = {
    "role_intake_scorecard": UseCasePolicy(
        chain=[
            ProviderChoice(Provider.OPENROUTER, "anthropic/claude-sonnet-5"),
            ProviderChoice(Provider.GEMINI, "gemini-flash-latest"),
        ],
        rationale=(
            "Large/complex tier: competency design and structured reasoning "
            "over business context benefits from frontier-model quality. "
            "Routed via OpenRouter to Claude Sonnet 5 since no OpenAI key "
            "is currently available; Gemini flash as a same-availability "
            "fallback rather than leaving this use case with no working path."
        ),
    ),
    "resume_parsing": UseCasePolicy(
        chain=[
            ProviderChoice(Provider.GROQ, "llama-3.1-8b-instant"),
            ProviderChoice(Provider.GEMINI, "gemini-flash-latest"),
        ],
        rationale=(
            "Small/high-volume tier: structured extraction from a resume is "
            "well within a small model's capability and runs per-candidate, "
            "so Groq's small model (cheapest, fastest) is the primary; "
            "Gemini flash as fallback for availability."
        ),
    ),
    "evidence_matching": UseCasePolicy(
        chain=[
            ProviderChoice(Provider.GROQ, "llama-3.3-70b-versatile"),
            ProviderChoice(Provider.GEMINI, "gemini-flash-latest"),
        ],
        rationale=(
            "Medium tier: low-cost first pass over evidence-to-criteria "
            "matching, escalate ambiguous/senior-role cases manually rather "
            "than routing to a larger model automatically (no escalation "
            "tier wired up yet). Groq's larger model balances quality and "
            "the pass's high call volume."
        ),
    ),
    "interview_evaluation": UseCasePolicy(
        chain=[
            ProviderChoice(Provider.OPENROUTER, "anthropic/claude-sonnet-5"),
            ProviderChoice(Provider.GEMINI, "gemini-flash-latest"),
        ],
        rationale=(
            "Large/complex tier: evaluating interview evidence against a "
            "fixed rubric needs higher reasoning quality than a small/medium "
            "model reliably gives — same tier as role_intake_scorecard."
        ),
    ),
    "candidate_report": UseCasePolicy(
        chain=[
            ProviderChoice(Provider.GEMINI, "gemini-flash-latest"),
            ProviderChoice(Provider.GROQ, "llama-3.3-70b-versatile"),
        ],
        rationale=(
            "Medium tier: generates an explanation only from already-stored "
            "evidence and scores (no new judgment), so a mid-size model is "
            "sufficient. Gemini flash primary, Groq's larger model as fallback."
        ),
    ),
    "voice_interview_turn": UseCasePolicy(
        chain=[
            ProviderChoice(
                Provider.OPENROUTER, "nvidia/nemotron-3-nano-30b-a3b:free", timeout_s=8.0
            ),
            ProviderChoice(Provider.GEMINI, "gemini-flash-latest"),
            ProviderChoice(Provider.GROQ, "llama-3.3-70b-versatile"),
        ],
        rationale=(
            "Realtime conversational turn generation for the Voice "
            "Interviewer (PRD Section 7.1); bounded by voice_agent's "
            "system-prompt guardrails, no scoring or rubric authority "
            "(ADR-0003). Reordered from pure Groq-first latency optimization "
            "after live testing repeatedly exhausted Groq's 100k/day token "
            "cap and Gemini's 5 req/min free-tier cap *simultaneously* during "
            "heavy dev testing, leaving the interview with no working "
            "provider at all. A free-tier OpenRouter model (benchmarked live: "
            "~1.6s TTFT, reliable, decent conversational quality — see "
            "session notes) is now first since it draws from neither quota; "
            "Gemini and Groq remain as the 2nd/3rd tier for quality/latency "
            "once a real interview's volume is nowhere near exhausting them. "
            "Revisit ordering (Groq first) once Groq's tier/quota is raised "
            "for production, where latency matters more than during rapid "
            "dev iteration. STT/TTS stay on Deepgram/ElevenLabs (audio-only, "
            "not a reasoning surface — see voice_agent/gateway_llm.py's "
            "module docstring)."
        ),
    ),
    "voice_interview_summary": UseCasePolicy(
        chain=[
            ProviderChoice(
                Provider.OPENROUTER, "nvidia/nemotron-3-nano-30b-a3b:free", timeout_s=8.0
            ),
            ProviderChoice(Provider.GEMINI, "gemini-flash-latest"),
            ProviderChoice(Provider.GROQ, "llama-3.3-70b-versatile"),
        ],
        rationale=(
            "Background conversation-memory consolidation for the Voice "
            "Interviewer (see voice_agent/gateway_llm.py's rolling summary) "
            "— not latency-critical, so the same quota-exhaustion reasoning "
            "as voice_interview_turn applies even more directly here: this "
            "runs every few turns regardless, so it's often what actually "
            "burns through Gemini's per-minute cap first. Same reordering, "
            "same rationale. Same boundaries as voice_interview_turn: no "
            "scoring, no rubric authority (ADR-0003)."
        ),
    ),
    "role_discovery_turn": UseCasePolicy(
        chain=[
            ProviderChoice(
                Provider.OPENROUTER, "nvidia/nemotron-3-nano-30b-a3b:free", timeout_s=8.0
            ),
            ProviderChoice(Provider.GEMINI, "gemini-flash-latest"),
            ProviderChoice(Provider.GROQ, "llama-3.3-70b-versatile"),
        ],
        rationale=(
            "Realtime conversational turn generation for the Hiring Manager "
            "Discovery Agent (see voice_agent/discovery_llm.py) — same "
            "quota-exhaustion reasoning and reordering as voice_interview_turn. "
            "This agent only collects structured intake data; it never "
            "generates or publishes a rubric itself (see hireOsBe/CLAUDE.md's "
            "Role Context Agent boundary)."
        ),
    ),
    "role_discovery_extraction": UseCasePolicy(
        chain=[
            ProviderChoice(
                Provider.OPENROUTER, "nvidia/nemotron-3-nano-30b-a3b:free", timeout_s=8.0
            ),
            ProviderChoice(Provider.GEMINI, "gemini-flash-latest"),
            ProviderChoice(Provider.GROQ, "llama-3.3-70b-versatile"),
        ],
        rationale=(
            "Background structured-field extraction for the Hiring Manager "
            "Discovery Agent (see voice_agent/discovery_llm.py) — runs after "
            "every single turn via model_gateway.run_structured(), so like "
            "voice_interview_summary this is often what burns through a "
            "per-minute quota first. Same reordering, same rationale. "
            "Extraction output is intake data only — never a rubric or "
            "hiring decision."
        ),
    ),
}


def get_policy(use_case: str) -> UseCasePolicy:
    if use_case not in USE_CASE_POLICIES:
        raise KeyError(f"No routing policy defined for use case '{use_case}'")
    return USE_CASE_POLICIES[use_case]
