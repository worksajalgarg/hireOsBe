"""
Voice Interviewer boundary (PRD Section 7.1). Hard boundary: cannot change
rubric/recommendation policy or access other candidates. Voice runtime lands
in Sprint 6 per the roadmap.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/interview-orchestrator", tags=["interview-orchestrator"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"agent": "interview-orchestrator", "status": "not implemented — Sprint 6"}
