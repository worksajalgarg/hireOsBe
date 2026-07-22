"""
Evaluation Agent boundary (PRD Section 7.1). Hard boundary: cannot issue a
final hiring decision — output is always a CandidateEvaluation with a
recommendation field, never a decision field. Implementation lands in
Sprint 7 (Voice evaluation alpha).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/evaluation-engine", tags=["evaluation-engine"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"agent": "evaluation-engine", "status": "not implemented — Sprint 7"}
