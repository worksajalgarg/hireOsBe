"""
Per-use-case model routing policy, matching the PRD's "AI model strategy by
module" table. Kept as a plain data structure (not hidden in agent code) so
routing decisions are auditable and changeable without touching agent logic.
"""

from dataclasses import dataclass

from .providers import Provider


@dataclass(frozen=True)
class UseCasePolicy:
    primary: Provider
    fallback: Provider | None
    rationale: str


# Final ranking deliberately has no entry here: PRD Section 7.2 / roadmap
# Section 5 — final ranking uses no LLM at all, only deterministic scoring.
USE_CASE_POLICIES: dict[str, UseCasePolicy] = {
    "role_intake_scorecard": UseCasePolicy(
        primary=Provider.OPENAI,
        fallback=Provider.ANTHROPIC,
        rationale="Complex business context, competency design and structured reasoning.",
    ),
    "resume_parsing": UseCasePolicy(
        primary=Provider.OPENAI,
        fallback=Provider.GEMINI,
        rationale="High-volume structured extraction; multimodal/PDF challenger.",
    ),
    "evidence_matching": UseCasePolicy(
        primary=Provider.OPENAI,
        fallback=Provider.ANTHROPIC,
        rationale="Low-cost first pass; escalate ambiguity and senior roles.",
    ),
    "interview_evaluation": UseCasePolicy(
        primary=Provider.OPENAI,
        fallback=Provider.ANTHROPIC,
        rationale="Higher reasoning quality against a fixed rubric.",
    ),
    "candidate_report": UseCasePolicy(
        primary=Provider.OPENAI,
        fallback=None,
        rationale="Generate explanation only from stored evidence and scores.",
    ),
}


def get_policy(use_case: str) -> UseCasePolicy:
    if use_case not in USE_CASE_POLICIES:
        raise KeyError(f"No routing policy defined for use case '{use_case}'")
    return USE_CASE_POLICIES[use_case]
