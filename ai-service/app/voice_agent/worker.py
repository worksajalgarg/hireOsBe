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
from .session import build_agent_session, build_interview_agent

logger = logging.getLogger("voice_agent")


def _room_metadata(ctx: JobContext) -> dict:
    """Room metadata is set by platform/src/interviews/interviews.service.ts
    at room-creation time and is the only source of tenant/session identity
    this process ever sees — it never calls back into platform, and never
    receives another candidate's session id."""
    raw = ctx.room.metadata or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Room %s has non-JSON metadata, proceeding without it", ctx.room.name)
        return {}


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    metadata = _room_metadata(ctx)
    logger.info(
        "voice_agent dispatched",
        extra={
            "room": ctx.room.name,
            "tenantId": metadata.get("tenantId"),
            "sessionId": metadata.get("sessionId"),
        },
    )

    session: AgentSession = build_agent_session()
    agent = build_interview_agent()
    await session.start(agent=agent, room=ctx.room)
    register_control_handlers(ctx.room, session)


def main() -> None:
    load_settings()  # fail fast if LIVEKIT_*/GEMINI_API_KEY/etc are missing
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
