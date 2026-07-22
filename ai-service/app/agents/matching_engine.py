"""
Evidence-based matching (rules + embeddings + LLM escalation per PRD Section
5). Final ranking itself is never produced here — that stays deterministic,
outside any LLM path. Implementation lands in Sprint 3.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/matching-engine", tags=["matching-engine"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"agent": "matching-engine", "status": "not implemented — Sprint 3"}
