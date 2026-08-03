"""Post-call interview evaluation shape — posted to platform's
POST /internal/interview-sessions/:id/transcript alongside the raw
transcript (see transcript_delivery.py, worker.py's shutdown callback).

Deliberately NOT platform's full CandidateEvaluation type (which requires
roleId/rubricVersion — no rubric/role-context system exists yet, see
hireOsBe/docs/adr/0006-interview-transcript-storage.md). This is a
scoped-down, evidence-based shape: no bare score, ever (ADR-0003), reusing
the same `recommendation` values a full CandidateEvaluation will also use,
so this is forward-compatible rather than a shape that gets thrown away
later.

Field names are camelCase (via `to_camel` aliasing) to match
platform/src/interviews/internal-dto.ts's IngestTranscriptDto exactly —
this model's only job is producing that JSON body, not idiomatic Python
attribute access.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

EvidenceStrength = Literal["strong", "moderate", "weak", "missing"]
EvaluationRecommendation = Literal[
    "strong_review", "review", "further_assessment", "insufficient_data"
]


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TopicEvaluation(_CamelModel):
    topic: str
    question_asked: str
    response_summary: str
    evidence_strength: EvidenceStrength
    supporting_evidence: list[str]
    missing_evidence: list[str]


class EvaluationLLMOutput(_CamelModel):
    """What the eval LLM actually produces — the model has no reliable way
    to self-report which provider/model served it or a real timestamp, so
    those fields aren't asked for here; post_call_evaluation.py fills them
    in programmatically to build the full InterviewEvaluationSummary."""

    recommendation: EvaluationRecommendation
    overall_assessment: str
    topics: list[TopicEvaluation]


class InterviewEvaluationSummary(_CamelModel):
    candidate_ref: str
    recommendation: EvaluationRecommendation
    overall_assessment: str
    topics: list[TopicEvaluation]
    model_version: str
    generated_at: str
