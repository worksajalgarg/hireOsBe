"""LiveKit Agents worker entrypoint. Runs as its own long-lived process,
separate from the FastAPI app (`uvicorn app.main:app`) — livekit-agents
workers hold a persistent connection to livekit-server and get dispatched
into rooms directly by the server, they are not HTTP handlers. Run with:

    python -m app.voice_agent.worker start

See app/agents/interview_orchestrator.py for the narrow FastAPI-side
boundary (orchestration metadata only); this module is where the interview
is actually conducted.
"""

import json
import logging

from livekit.agents import AgentSession, JobContext, WorkerOptions, cli
from livekit.agents.job import AutoSubscribe

from .config import load_settings
from .controls import register_control_handlers
from .prompts import build_interview_system_prompt
from .session import build_agent_session, build_interview_agent

logger = logging.getLogger("voice_agent")


def _room_metadata(ctx: JobContext) -> dict:
    """Room metadata is set by platform/src/interviews/interviews.service.ts
    at room-creation time and is the only source of tenant/session identity
    (and, optionally, resumeContext) this process ever sees — it never calls
    back into platform, and never receives another candidate's session id."""
    raw = ctx.room.metadata or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Room %s has non-JSON metadata, proceeding without it", ctx.room.name)
        return {}


async def entrypoint(ctx: JobContext) -> None:
    # AUDIO_ONLY is a deliberate, structural Responsible AI boundary, not an
    # oversight — do not change this to subscribe to video. The candidate's
    # camera may be published and recorded (see platform's Egress config),
    # but this agent process must never receive a video frame: that's what
    # keeps facial/emotion/behavioral inference structurally impossible here,
    # not just prompt-discouraged. See hireOsBe/CLAUDE.md's "Explicitly NOT
    # building" list (proctoring/anti-cheating surveillance, facial/emotion
    # inference) and the Responsible AI constraints section.
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    metadata = _room_metadata(ctx)
    logger.info(
        "voice_agent dispatched",
        extra={
            "room": ctx.room.name,
            "tenantId": metadata.get("tenantId"),
            "sessionId": metadata.get("sessionId"),
            "hasResumeContext": bool(metadata.get("resumeContext")),
        },
    )

    system_prompt = build_interview_system_prompt(metadata.get("resumeContext"))
    session: AgentSession = build_agent_session(system_prompt)
    agent = build_interview_agent(system_prompt)
    await session.start(agent=agent, room=ctx.room)
    register_control_handlers(ctx.room, session)


def main() -> None:
    load_settings()  # fail fast if LIVEKIT_*/GEMINI_API_KEY/etc are missing
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
