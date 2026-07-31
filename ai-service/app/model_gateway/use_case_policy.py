"""
Per-use-case model routing policy, matching the PRD's "AI model strategy by
module" table. Kept as a plain data structure (not hidden in agent code) so
routing decisions are auditable and changeable without touching agent logic.

Provider tiering (no working OpenAI key at present — Gemini/Groq/OpenRouter
are the live providers):
- small/high-volume, low-reasoning work -> Groq's small model (fastest, cheapest)
- medium reasoning / synthesis          -> Groq's larger model or Gemini flash
- large/complex reasoning               -> OpenRouter routed to a frontier
  model (Claude 3.5 Sonnet) — the only path to top-tier reasoning quality
  without an OpenAI key
- realtime voice turn generation        -> Groq (lowest per-token latency of
  the three, matters most on this latency-critical path)
"""

from dataclasses import dataclass

from .providers import Provider


@dataclass(frozen=True)
class UseCasePolicy:
    primary: Provider
    primary_model: str | None
    fallback: Provider | None
    fallback_model: str | None
    rationale: str


# Final ranking deliberately has no entry here: PRD Section 7.2 / roadmap
# Section 5 — final ranking uses no LLM at all, only deterministic scoring.
USE_CASE_POLICIES: dict[str, UseCasePolicy] = {
    "role_intake_scorecard": UseCasePolicy(
        primary=Provider.OPENROUTER,
        primary_model="anthropic/claude-sonnet-5",
        fallback=Provider.GEMINI,
        fallback_model="gemini-flash-latest",
        rationale=(
            "Large/complex tier: competency design and structured reasoning "
            "over business context benefits from frontier-model quality. "
            "Routed via OpenRouter to Claude Sonnet 5 since no OpenAI key "
            "is currently available; Gemini flash as a same-availability "
            "fallback rather than leaving this use case with no working path."
        ),
    ),
    "resume_parsing": UseCasePolicy(
        primary=Provider.GROQ,
        primary_model="llama-3.1-8b-instant",
        fallback=Provider.GEMINI,
        fallback_model="gemini-flash-latest",
        rationale=(
            "Small/high-volume tier: structured extraction from a resume is "
            "well within a small model's capability and runs per-candidate, "
            "so Groq's small model (cheapest, fastest) is the primary; "
            "Gemini flash as fallback for availability."
        ),
    ),
    "evidence_matching": UseCasePolicy(
        primary=Provider.GROQ,
        primary_model="llama-3.3-70b-versatile",
        fallback=Provider.GEMINI,
        fallback_model="gemini-flash-latest",
        rationale=(
            "Medium tier: low-cost first pass over evidence-to-criteria "
            "matching, escalate ambiguous/senior-role cases manually rather "
            "than routing to a larger model automatically (no escalation "
            "tier wired up yet). Groq's larger model balances quality and "
            "the pass's high call volume."
        ),
    ),
    "interview_evaluation": UseCasePolicy(
        primary=Provider.OPENROUTER,
        primary_model="anthropic/claude-sonnet-5",
        fallback=Provider.GEMINI,
        fallback_model="gemini-flash-latest",
        rationale=(
            "Large/complex tier: evaluating interview evidence against a "
            "fixed rubric needs higher reasoning quality than a small/medium "
            "model reliably gives — same tier as role_intake_scorecard."
        ),
    ),
    "candidate_report": UseCasePolicy(
        primary=Provider.GEMINI,
        primary_model="gemini-flash-latest",
        fallback=Provider.GROQ,
        fallback_model="llama-3.3-70b-versatile",
        rationale=(
            "Medium tier: generates an explanation only from already-stored "
            "evidence and scores (no new judgment), so a mid-size model is "
            "sufficient. Gemini flash primary, Groq's larger model as fallback."
        ),
    ),
    "voice_interview_turn": UseCasePolicy(
        primary=Provider.GROQ,
        primary_model="llama-3.3-70b-versatile",
        fallback=Provider.GEMINI,
        fallback_model="gemini-flash-latest",
        rationale=(
            "Realtime conversational turn generation for the Voice "
            "Interviewer (PRD Section 7.1); bounded by voice_agent's "
            "system-prompt guardrails, no scoring or rubric authority "
            "(ADR-0003). Latency-critical path — Groq's LPU inference has "
            "the lowest per-token latency of the available providers, "
            "directly reducing the LLM-call-to-TTS-playback gap. Gemini "
            "(already proven live) as fallback. STT/TTS stay on Deepgram/"
            "ElevenLabs (audio-only, not a reasoning surface — see "
            "voice_agent/gateway_llm.py's module docstring)."
        ),
    ),
    "voice_interview_summary": UseCasePolicy(
        primary=Provider.GEMINI,
        primary_model="gemini-flash-latest",
        fallback=Provider.GROQ,
        fallback_model="llama-3.3-70b-versatile",
        rationale=(
            "Background conversation-memory consolidation for the Voice "
            "Interviewer (see voice_agent/gateway_llm.py's rolling summary) "
            "— runs off the response critical path between turns, so unlike "
            "voice_interview_turn it doesn't need Groq's latency edge. "
            "Gemini stays primary (already proven live); Groq as fallback. "
            "Same boundaries as voice_interview_turn: no scoring, no rubric "
            "authority (ADR-0003)."
        ),
    ),
}


def get_policy(use_case: str) -> UseCasePolicy:
    if use_case not in USE_CASE_POLICIES:
        raise KeyError(f"No routing policy defined for use case '{use_case}'")
    return USE_CASE_POLICIES[use_case]
