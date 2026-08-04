"""LiveKit Agents worker entrypoint. Runs as its own long-lived process,
separate from the FastAPI app (`uvicorn app.main:app`) — livekit-agents
workers hold a persistent connection to livekit-server and get dispatched
into rooms directly by the server, they are not HTTP handlers. Run with:

    python -m app.voice_agent.worker start

Use `start`, not `dev`/`console`, for anything meant to run unattended.
`start` is the only mode that gets structured JSON-to-stdout logging
(confirmed from livekit-agents' own cli/log.py: `dev`/`console` force
devmode=True, which uses colored, human-only, non-machine-parseable
output instead) — every logger in this process, including
model_gateway.metrics, rides on that same root-logger handler with no
further setup needed here. See app/main.py's `_configure_logging()` for
the FastAPI process's equivalent.

Handles two personas, chosen by room metadata's sessionType:
- "candidate_interview" (default) — the candidate-facing screening
  interview (see prompts.py, gateway_llm.py).
- "hiring_manager_discovery" — the Hiring Manager Discovery Agent (see
  hiring_manager_prompts.py, discovery_llm.py), a structured intake
  conversation with a hiring manager, not a candidate.

See app/agents/interview_orchestrator.py for the narrow FastAPI-side
boundary (orchestration metadata only); this module is where the
conversation is actually conducted, for either persona.

Room metadata (read by _room_metadata() below) is still the only *inbound*
channel from platform — this process never fetches config or session state
from platform before/during a call. The one deliberate exception is
*outbound*: after a candidate_interview call ends, entrypoint()'s shutdown
callback POSTs the transcript + evaluation to platform (see
transcript_delivery.py, docs/adr/0006-interview-transcript-storage.md) —
strictly post-call and best-effort (local outbox + retry), so a platform
outage delays persistence, never the interview itself.
"""

import asyncio
import hashlib
import json
import logging
import os
import threading
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import AgentServer, AgentSession, JobContext, JobProcess, cli
from livekit.agents.job import AutoSubscribe
try:
    from livekit.plugins import silero
except ImportError:
    silero = None

from ..model_gateway.gateway import model_gateway
from ..model_gateway.metrics_log import reset_dev_metrics
from ..model_gateway.providers import Provider
from ..model_gateway.routing_config import load_routing_config
from ..model_gateway.use_case_policy import USE_CASE_POLICIES, apply_provider_priority
from .config import LIVEKIT_INFERENCE, VoiceAgentSettings, load_settings
from .controls import register_control_handlers
from .conversation_start import register_silence_handling
from .dev_metrics import is_dev_metrics_enabled, register_dev_metrics_listener
from .hiring_manager_prompts import (
    DISCOVERY_OPENING_INSTRUCTIONS,
    DISCOVERY_SILENCE_NUDGE_INSTRUCTIONS,
    HIRING_MANAGER_DISCOVERY_SYSTEM_PROMPT,
)
from .llm_streaming import extract_structured_transcript
from .metadata_signing import verify_metadata_signature
from .post_call_evaluation import evaluate_interview
from .prompts import (
    CANDIDATE_OPENING_INSTRUCTIONS,
    CANDIDATE_SILENCE_NUDGE_INSTRUCTIONS,
    build_interview_system_prompt,
)
from .session import (
    build_agent_session,
    build_discovery_agent_session,
    build_room_options,
    build_voice_agent,
)
from .transcript_delivery import deliver_transcript, flush_pending

logger = logging.getLogger("voice_agent")

# AgentServer (not WorkerOptions+cli.run_app(WorkerOptions(...))) — the
# newer livekit-agents registration surface over the same underlying
# job-process-pool architecture (JobContext/room-metadata/persona-picking
# below are unaffected). setup_fnc below prewarms Silero VAD once per idle
# process instead of session.py reloading it on every single dispatch.
# shutdown_process_timeout raised from the framework's 10s default — the
# post-call transcript build + evaluation LLM call + POST to platform (see
# entrypoint()'s shutdown callback) needs real headroom, same reasoning the
# reference demo project's AgentServer(shutdown_process_timeout=60.0) used.
server = AgentServer(
    port=int(os.environ.get("PORT", 8081)),
    shutdown_process_timeout=60.0,
    initialize_process_timeout=60.0,
    num_idle_processes=0,
)


def _prewarm(proc: JobProcess) -> None:
    # Loaded off the process-init critical path: Silero's ONNX runtime does a
    # GPU device scan that can take ~35s on constrained cloud containers,
    # which previously blew past initialize_process_timeout when loaded
    # synchronously here. entrypoint() waits (bounded) on vad_ready instead
    # of blocking process spawn on this.
    vad_ready = threading.Event()
    proc.userdata["vad_ready"] = vad_ready

    def _load() -> None:
        try:
            if silero is not None:
                proc.userdata["vad"] = silero.VAD.load()
        except Exception as exc:
            logger.warning("Silero VAD prewarm failed: %s", exc)
        finally:
            vad_ready.set()

    threading.Thread(target=_load, daemon=True).start()


server.setup_fnc = _prewarm

CANDIDATE_INTERVIEW = "candidate_interview"
HIRING_MANAGER_DISCOVERY = "hiring_manager_discovery"

# Only these four use cases were ever affected by today's quota-exhaustion
# reordering (see use_case_policy.py) — the non-voice use cases keep their
# own hardcoded chains regardless of VOICE_LLM_PROVIDER_PRIORITY.
_VOICE_LLM_USE_CASES = [
    "voice_interview_turn",
    "voice_interview_summary",
    "role_discovery_turn",
    "role_discovery_extraction",
]

# Reloaded once per job dispatch (see entrypoint()) so a routing_config.yaml
# edit takes effect for the next interview without a full worker restart —
# not mid-interview (a chain mutated while a run_stream() call is in flight
# is a real race), just at the next dispatch boundary. Cached by mtime so an
# unchanged file is a cheap stat(), not a re-parse.
#
# entrypoint() calls load_settings() itself (below) rather than reading a
# module global main() populated — livekit-agents dispatches jobs into a
# pool of separate child processes (see this module's docstring and the
# "initializing process" log lines at worker startup), each with its own
# fresh import of this module, so a global set in main()'s process (the
# supervisor) is never visible to entrypoint()'s process. Environment
# variables ARE inherited by child processes, so load_settings() itself
# works fine there — it's specifically Python-level module globals that
# don't cross the boundary. (Confirmed the hard way: entrypoint() used to
# gate this reload on such a global, silently skipping it in the child and
# leaving USE_CASE_POLICIES empty — KeyError: "No routing policy defined
# for use case 'voice_interview_turn'" on the first real interview turn.)
_routing_config_mtime: float | None = None


def _reload_routing_config_if_changed(
    path: Path, priority: list[Provider], settings: VoiceAgentSettings
) -> None:
    global _routing_config_mtime
    try:
        mtime = path.stat().st_mtime
    except OSError:
        logger.warning("Routing config %s not found, keeping previously loaded policies", path)
        return
    if mtime == _routing_config_mtime:
        # Even if YAML is unchanged, re-apply livekit_inference mode if needed
        # (child processes start with an empty USE_CASE_POLICIES and need this
        # regardless of whether the file changed).
        if settings.voice_provider == LIVEKIT_INFERENCE:
            model_gateway.set_livekit_inference_mode(
                primary=settings.llm_model,
                fallbacks=settings.llm_fallback_models,
            )
        return
    USE_CASE_POLICIES.clear()
    USE_CASE_POLICIES.update(load_routing_config(path))
    apply_provider_priority(_VOICE_LLM_USE_CASES, priority)
    _routing_config_mtime = mtime
    # After loading/reloading the YAML, replace voice use-case chains with
    # livekit_inference tiers if that mode is active.
    if settings.voice_provider == LIVEKIT_INFERENCE:
        model_gateway.set_livekit_inference_mode(
            primary=settings.llm_model,
            fallbacks=settings.llm_fallback_models,
        )


def _room_metadata(ctx: JobContext) -> dict:
    """Room metadata is set by platform/src/interviews/interviews.service.ts
    at room-creation time and is the only *inbound* source of tenant/session
    identity (and, optionally, resumeContext/sessionType) this process ever
    sees — it never fetches anything from platform before/during a call,
    and never receives another session's data. (Module docstring above
    covers the one deliberate outbound exception: post-call transcript
    delivery.)"""
    raw = ctx.room.metadata or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Room %s has non-JSON metadata, proceeding without it", ctx.room.name)
        return {}


@server.rtc_session()
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

    settings = load_settings()
    import hashlib as _hashlib  # TEMP DIAGNOSTIC — remove after debugging
    logger.warning(
        "TEMP_DIAG internal_service_secret len=%d sha256_8=%s",
        len(settings.internal_service_secret),
        _hashlib.sha256(settings.internal_service_secret.encode()).hexdigest()[:8],
    )
    _reload_routing_config_if_changed(
        settings.routing_config_path, settings.llm_provider_priority, settings
    )

    if is_dev_metrics_enabled():
        # One dashboard, one interview at a time locally — reset at the
        # start of each dispatch so it never shows a mix of past sessions.
        reset_dev_metrics()

    metadata = _room_metadata(ctx)

    # Reject a room whose metadata wasn't signed by platform's createSession()
    # (see room-metadata-signing.ts, metadata_signing.py, and
    # docs/adr/0006-interview-transcript-storage.md's Phase E section) —
    # fails closed: no session is built, no STT/LLM/TTS cost is incurred,
    # for a room that didn't come from platform's own session creation.
    is_console_room = ctx.room.name in ("console", "console-room") or ctx.room.name.startswith(
        "console"
    )
    if not is_console_room and not verify_metadata_signature(
        metadata, settings.internal_service_secret
    ):
        logger.error(
            "Room %s has missing/invalid metadata signature — refusing to start a session",
            ctx.room.name,
        )
        ctx.shutdown(reason="invalid room metadata signature")
        return

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

    vad_ready = ctx.proc.userdata.get("vad_ready")
    if vad_ready is not None and not vad_ready.is_set():
        # First job to land on a process whose background VAD load (see
        # _prewarm) hasn't finished yet — give it a bounded grace period
        # rather than blocking process init on the full ~35s load.
        await asyncio.to_thread(vad_ready.wait, 10.0)
    vad = ctx.proc.userdata.get("vad")
    if vad is None:
        logger.warning("Starting session without VAD (prewarm not ready or failed)")
    if session_type == HIRING_MANAGER_DISCOVERY:
        system_prompt = HIRING_MANAGER_DISCOVERY_SYSTEM_PROMPT
        opening_instructions = DISCOVERY_OPENING_INSTRUCTIONS
        nudge_instructions = DISCOVERY_SILENCE_NUDGE_INSTRUCTIONS
        session: AgentSession = build_discovery_agent_session(
            system_prompt, session_label=ctx.room.name, vad=vad
        )
    else:
        prompt_ctx_str = metadata.get("promptContext")
        prompt_data = {}
        if prompt_ctx_str:
            try:
                prompt_data = json.loads(prompt_ctx_str)
            except Exception:
                pass

        flow = prompt_data.get("conversationFlow")
        boundaries = prompt_data.get("systemBoundaries")
        opening = prompt_data.get("openingInstructions")
        silence = prompt_data.get("silenceInstructions")

        system_prompt = build_interview_system_prompt(
            metadata.get("resumeContext"),
            conversation_flow=flow,
            system_boundaries=boundaries,
        )
        opening_instructions = opening or CANDIDATE_OPENING_INSTRUCTIONS
        nudge_instructions = silence or CANDIDATE_SILENCE_NUDGE_INSTRUCTIONS
        session = build_agent_session(system_prompt, session_label=ctx.room.name, vad=vad)

    agent = build_voice_agent(system_prompt, opening_instructions=opening_instructions)
    await session.start(agent=agent, room=ctx.room, room_options=build_room_options(settings))
    register_control_handlers(ctx.room, session)
    register_silence_handling(session, nudge_instructions=nudge_instructions)
    if is_dev_metrics_enabled():
        register_dev_metrics_listener(session, ctx.room.name)

    # Candidate-interview only for this pass — the discovery agent's
    # structured intake data (DiscoveryFields) is a different shape with no
    # "evaluation"/recommendation concept, and isn't covered by this
    # endpoint yet (see docs/adr/0006-interview-transcript-storage.md).
    if session_type == CANDIDATE_INTERVIEW:
        ctx.add_shutdown_callback(
            _deliver_transcript_on_shutdown(
                session=session,
                settings=settings,
                tenant_id=metadata.get("tenantId"),
                session_id=metadata.get("sessionId"),
                system_prompt=system_prompt,
            )
        )


def _deliver_transcript_on_shutdown(
    *,
    session: AgentSession,
    settings: VoiceAgentSettings,
    tenant_id: str | None,
    session_id: str | None,
    system_prompt: str,
):
    """Returns the actual shutdown-callback coroutine function — a closure
    so it captures this dispatch's session/settings/ids without needing
    JobContext to carry them. Best-effort throughout: this must never raise
    into livekit-agents' shutdown sequence, and a failure here must never be
    interpreted as anything about the candidate (see CLAUDE.md's Responsible
    AI constraint: a technical/connection issue must never silently affect
    scoring — this is purely operational data delivery, not scoring)."""

    async def _on_shutdown() -> None:
        if not tenant_id or not session_id:
            logger.warning(
                "Skipping transcript delivery: missing tenantId/sessionId in room metadata"
            )
            return
        try:
            lines = extract_structured_transcript(
                session.history, user_label="Candidate", assistant_label="Interviewer"
            )
            flat_lines = [f"{line['speaker']}: {line['text']}" for line in lines]
            evaluation = await evaluate_interview(
                candidate_ref=session_id, transcript_lines=flat_lines
            )
            # Platform's internal DTO declares modelUsage as @IsObject()
            # (Record<string, unknown>) — must be a JSON object, not an
            # array. Key by index so all entries are preserved as a dict.
            raw_usage = [m.model_dump(mode="json") for m in session.usage.model_usage]
            model_usage_obj: dict = {str(i): entry for i, entry in enumerate(raw_usage)}
            payload = {
                "tenantId": tenant_id,
                "lines": lines,
                "rollingSummary": getattr(session.llm, "rolling_summary", None) or None,
                "evaluation": evaluation.model_dump(by_alias=True),
                "promptVersionsUsed": {
                    "candidate_interview": hashlib.sha256(system_prompt.encode()).hexdigest()[:12]
                },
                "modelUsage": model_usage_obj,
            }
            await deliver_transcript(
                session_id,
                payload,
                base_url=settings.platform_internal_url,
                secret=settings.internal_service_secret,
            )
        except Exception:
            logger.exception(
                "Unhandled error building/delivering transcript for session %s", session_id
            )

    return _on_shutdown


def main() -> None:
    # Loaded first, before load_settings() below reads os.environ. Does NOT
    # rely on the IDE/debugger's own envFile support — see app/main.py's
    # matching comment for why (a debugpy+module-launch quirk left env vars
    # unset even with envFile configured in launch.json). override=False
    # (the default) means real deployment env vars always win over this file.
    # Only covers this supervisor process — each job's child process (see
    # entrypoint()) inherits the environment from here regardless, so it
    # doesn't need its own load_dotenv() call.
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
    settings = load_settings()  # fail fast if required env vars are missing
    # Fail-fast validation of the routing config at supervisor startup, so a
    # broken YAML is caught immediately rather than on the first dispatched
    # job. This populates USE_CASE_POLICIES in the supervisor process only —
    # entrypoint() (below) does the real per-job-process load, since that's
    # a separate process this one doesn't share memory with.
    _reload_routing_config_if_changed(
        settings.routing_config_path, settings.llm_provider_priority, settings
    )
    # Retries any transcript a prior process wrote to the local outbox but
    # never successfully delivered (e.g. platform was down at the time) —
    # see transcript_delivery.py.
    asyncio.run(
        flush_pending(
            base_url=settings.platform_internal_url, secret=settings.internal_service_secret
        )
    )
    cli.run_app(server)


if __name__ == "__main__":
    main()
