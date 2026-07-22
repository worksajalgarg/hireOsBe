"""
Resume Evidence Agent boundary (PRD Section 7.1). Hard boundary: cannot
infer missing experience as fact. Implementation lands in Sprint 3.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/resume-intelligence", tags=["resume-intelligence"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"agent": "resume-intelligence", "status": "not implemented — Sprint 3"}
