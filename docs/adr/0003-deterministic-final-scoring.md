# 0003 — Final candidate ranking is deterministic, never LLM-produced

## Status
Accepted (Sprint 1)

## Context
The technical roadmap's AI decision principle states: *"Use the realtime model to conduct the interview, but use an offline evaluator against a versioned rubric. The final ranking is produced by a deterministic scoring engine. LLMs cannot modify weights, thresholds or eligibility rules."* This is also a Responsible AI requirement (PRD Section 8.3): no autonomous rejection, AI recommendation and human decision must remain separate fields.

## Decision
The Evaluation Agent (`services/ai-service/app/agents/evaluation_engine.py`) produces a `CandidateEvaluation` (see `packages/shared-types/src/evaluation.ts`) whose `recommendation` field is one of `strong_review | review | further_assessment | insufficient_data` — never a final hire/reject decision, and never a single opaque score. Scoring weights, thresholds, and eligibility rules are defined and applied outside any LLM call, in deterministic code owned by `apps/platform`. The AI service's `use_case_policy.py` has no routing entry for "final ranking" by design — there is nothing to route, because no model call happens at that step.

## Consequences
- A model provider outage, prompt regression, or hallucination can degrade evidence quality but cannot silently change who advances — the deterministic layer is the single source of truth for ranking.
- Every criterion score must carry `evidenceStrength`, `confidence`, `supportingEvidence`, and `missingEvidence` separately (never collapsed into one number), so a human reviewer can see the reasoning behind the deterministic outcome.
- Implementing the actual deterministic scoring engine (weights, thresholds, eligibility gates) is Sprint 7+ work (Voice evaluation alpha) — this ADR fixes the architectural constraint before that code exists, so it isn't designed around an LLM-produced score by mistake.
