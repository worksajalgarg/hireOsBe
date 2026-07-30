"""
Voice Interviewer boundary (PRD Section 7.1). Hard boundary: cannot change
rubric/recommendation policy or access other candidates.

This router is intentionally narrow: it's the HTTP-callable surface for
orchestration metadata only. The interview itself is conducted by the
livekit-agents worker in app/voice_agent/ (a separate long-lived process,
dispatched directly by livekit-server — not an HTTP handler, so it cannot
live here). See app/voice_agent/worker.py.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/interview-orchestrator", tags=["interview-orchestrator"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"agent": "interview-orchestrator", "status": "ok"}
