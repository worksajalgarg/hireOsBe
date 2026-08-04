"""Post-call structured evaluation of a completed candidate interview — the
ai-service side of docs/adr/0006-interview-transcript-storage.md. Runs once,
after the interview ends, through model_gateway's existing
`interview_evaluation` use case (already routed to a frontier-tier model —
see config/model_routing.yaml) — never a direct provider call, same
CTO-guardrail boundary every other use case in this codebase respects.

Deliberately does NOT produce a bare score or a hire/reject decision — see
evaluation_schema.py's module docstring for why the output shape is a
scoped-down InterviewEvaluationSummary, not platform's full
CandidateEvaluation (which needs a rubric system that doesn't exist yet).
"""

from datetime import datetime, timezone
from logging import getLogger

from ..model_gateway.gateway import model_gateway
from .evaluation_schema import EvaluationLLMOutput, InterviewEvaluationSummary

logger = getLogger("voice_agent")

USE_CASE = "interview_evaluation"

_EVALUATION_SYSTEM_PROMPT = """You are producing a post-interview evaluation of a candidate \
screening call for a human recruiter to review. Evaluate strictly based on what was actually \
said in the transcript provided — never invent, assume, or infer anything the candidate didn't \
actually say.

Respond with ONLY a single JSON object — no prose, no markdown code fences, no commentary \
before or after. Required shape:

{
  "recommendation": one of "strong_review" | "review" | "further_assessment" | "insufficient_data",
  "overallAssessment": "3-5 sentence neutral summary for the recruiter",
  "topics": [
    {
      "topic": "short label, e.g. 'Background' or 'System design experience'",
      "questionAsked": "the interviewer's actual question, verbatim or near-verbatim",
      "responseSummary": "1-2 sentence neutral summary of what the candidate said",
      "evidenceStrength": one of "strong" | "moderate" | "weak" | "missing",
      "supportingEvidence": ["specific quotes or paraphrases backing evidenceStrength"],
      "missingEvidence": ["what would have made this stronger, or empty if not applicable"]
    }
  ]
}

Rules:
- Never state, imply, or compute a numeric score — "recommendation" and per-topic
  "evidenceStrength" are the only judgments you make, and both must be traceable to
  supportingEvidence.
- "insufficient_data" is the correct recommendation when the call ended early, the candidate
  gave very few substantive answers, or there's a technical/connectivity issue — never let a
  short call read as a negative signal about the candidate.
- Never infer emotion, honesty, personality, or any trait not directly evidenced by what was
  said.
- One topics[] entry per distinct question actually asked and answered — do not fabricate
  topics that weren't covered."""


def build_transcript_text(lines: list[str]) -> str:
    return "\n".join(lines)


def _fallback_summary(candidate_ref: str, reason: str) -> InterviewEvaluationSummary:
    """Always returns a valid summary, never None — the transcript delivery
    payload requires an evaluation field (see worker.py's shutdown
    callback), so a failed eval call must degrade to this rather than
    causing the whole transcript to be dropped. "insufficient_data" is
    always the right call here per CLAUDE.md's Responsible AI constraint: a
    technical/evaluation failure must never read as a negative signal about
    the candidate."""
    return InterviewEvaluationSummary(
        candidate_ref=candidate_ref,
        recommendation="insufficient_data",
        overall_assessment=reason,
        topics=[],
        model_version=f"model_gateway:{USE_CASE}",
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


async def evaluate_interview(
    *, candidate_ref: str, transcript_lines: list[str]
) -> InterviewEvaluationSummary:
    """Never raises and never returns anything other than a valid summary —
    see _fallback_summary()'s docstring for why a failure degrades instead
    of dropping the transcript."""
    transcript = build_transcript_text(transcript_lines)
    if len(transcript) < 200 or len(transcript_lines) < 3:
        logger.info(
            "interview_evaluation skipped: transcript too short (%d chars, %d lines) — "
            "likely ended before the interview began",
            len(transcript), len(transcript_lines),
        )
        return _fallback_summary(
            candidate_ref, "The call ended before enough of the interview took place to evaluate."
        )

    try:
        llm_output = await model_gateway.run_structured(
            use_case=USE_CASE,
            system_prompt=_EVALUATION_SYSTEM_PROMPT,
            user_prompt=f"Transcript of the screening interview:\n\n{transcript}",
            schema=EvaluationLLMOutput,
        )
    except Exception:
        logger.exception("interview_evaluation failed for candidate_ref=%s", candidate_ref)
        return _fallback_summary(
            candidate_ref, "Automated evaluation could not be generated for this interview."
        )

    return InterviewEvaluationSummary(
        candidate_ref=candidate_ref,
        recommendation=llm_output.recommendation,
        overall_assessment=llm_output.overall_assessment,
        topics=llm_output.topics,
        model_version=f"model_gateway:{USE_CASE}",
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
