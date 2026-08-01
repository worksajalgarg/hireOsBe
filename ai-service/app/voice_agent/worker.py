"""LiveKit Agents worker entrypoint. Runs as its own long-lived process,
separate from the FastAPI app (`uvicorn app.main:app`) — livekit-agents
workers hold a persistent connection to livekit-server and get dispatched
into rooms directly by the server, they are not HTTP handlers. Run with:

    python -m app.voice_agent.worker start

Handles two personas, chosen by room metadata's sessionType:
- "candidate_interview" (default) — the candidate-facing screening
  interview (see prompts.py, gateway_llm.py).
- "hiring_manager_discovery" — the Hiring Manager Discovery Agent (see
  hiring_manager_prompts.py, discovery_llm.py), a structured intake
  conversation with a hiring manager, not a candidate.

See app/agents/interview_orchestrator.py for the narrow FastAPI-side
boundary (orchestration metadata only); this module is where the
conversation is actually conducted, for either persona.
"""

import json
import logging

from livekit.agents import AgentSession, JobContext, WorkerOptions, cli
from livekit.agents.job import AutoSubscribe

from ..model_gateway.metrics_log import reset_dev_metrics
from .config import load_settings
from .controls import register_control_handlers
from .conversation_start import register_silence_handling
from .dev_metrics import is_dev_metrics_enabled, register_dev_metrics_listener
from .hiring_manager_prompts import (
    DISCOVERY_OPENING_INSTRUCTIONS,
    DISCOVERY_SILENCE_NUDGE_INSTRUCTIONS,
    HIRING_MANAGER_DISCOVERY_SYSTEM_PROMPT,
)
from .prompts import (
    CANDIDATE_OPENING_INSTRUCTIONS,
    CANDIDATE_SILENCE_NUDGE_INSTRUCTIONS,
    build_interview_system_prompt,
)
from .session import build_agent_session, build_discovery_agent_session, build_voice_agent

logger = logging.getLogger("voice_agent")

CANDIDATE_INTERVIEW = "candidate_interview"
HIRING_MANAGER_DISCOVERY = "hiring_manager_discovery"


def _room_metadata(ctx: JobContext) -> dict:
    """Room metadata is set by platform/src/interviews/interviews.service.ts
    at room-creation time and is the only source of tenant/session identity
    (and, optionally, resumeContext/sessionType) this process ever sees — it
    never calls back into platform, and never receives another session's
    data."""
    raw = ctx.room.metadata or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Room %s has non-JSON metadata, proceeding without it", ctx.room.name)
        return {}


async def entrypoint(ctx: JobContext) -> None:
    # AUDIO_ONLY is a deliberate, structural Responsible AI boundary, not an
    # oversight — do not change this to subscribe to video, for either
    # persona. The candidate's camera may be published and recorded (see
    # platform's Egress config), but this agent process must never receive a
    # video frame: that's what keeps facial/emotion/behavioral inference
    # structurally impossible here, not just prompt-discouraged. See
    # hireOsBe/CLAUDE.md's "Explicitly NOT building" list (proctoring/
    # anti-cheating surveillance, facial/emotion inference) and the
    # Responsible AI constraints section.
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    if is_dev_metrics_enabled():
        # One dashboard, one interview at a time locally — reset at the
        # start of each dispatch so it never shows a mix of past sessions.
        reset_dev_metrics()

    metadata = _room_metadata(ctx)
    session_type = metadata.get("sessionType", CANDIDATE_INTERVIEW)
    logger.info(
        "voice_agent dispatched",
        extra={
            "room": ctx.room.name,
            "tenantId": metadata.get("tenantId"),
            "sessionId": metadata.get("sessionId"),
            "sessionType": session_type,
            "hasResumeContext": bool(metadata.get("resumeContext")),
        },
    )

    if session_type == HIRING_MANAGER_DISCOVERY:
        system_prompt = HIRING_MANAGER_DISCOVERY_SYSTEM_PROMPT
        opening_instructions = DISCOVERY_OPENING_INSTRUCTIONS
        nudge_instructions = DISCOVERY_SILENCE_NUDGE_INSTRUCTIONS
        session: AgentSession = build_discovery_agent_session(
            system_prompt, session_label=ctx.room.name
        )
    else:
        system_prompt = build_interview_system_prompt(metadata.get("resumeContext"))
        opening_instructions = CANDIDATE_OPENING_INSTRUCTIONS
        nudge_instructions = CANDIDATE_SILENCE_NUDGE_INSTRUCTIONS
        session = build_agent_session(system_prompt, session_label=ctx.room.name)

    agent = build_voice_agent(system_prompt, opening_instructions=opening_instructions)
    await session.start(agent=agent, room=ctx.room)
    register_control_handlers(ctx.room, session)
    register_silence_handling(session, nudge_instructions=nudge_instructions)
    if is_dev_metrics_enabled():
        register_dev_metrics_listener(session, ctx.room.name)


def main() -> None:
    load_settings()  # fail fast if LIVEKIT_*/GEMINI_API_KEY/etc are missing
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
