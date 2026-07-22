"""
Role Context Agent boundary (PRD Section 7.1). Hard boundary: cannot publish
a rubric without user approval — that approval gate belongs to apps/platform
(role-context module), not here. Implementation lands in Sprint 2.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/role-intelligence", tags=["role-intelligence"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"agent": "role-intelligence", "status": "not implemented — Sprint 2"}
