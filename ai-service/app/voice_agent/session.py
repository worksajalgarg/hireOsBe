"""Builds the AgentSession for a dispatched room: Silero VAD + STT/TTS
(audio-only, no reasoning surface — see gateway_llm.py's module docstring
for why these are the one deliberate exception to the model-gateway
boundary) and the gateway-routed LLM for the conversational turn itself.

Two personas share this STT/TTS/VAD construction and only differ in which
LLM class drives the conversation — GatewayLLM (candidate interview) or
DiscoveryLLM (hiring manager discovery, see discovery_llm.py); worker.py
picks which builder to call based on room metadata's sessionType.

STT/TTS come from one of two switchable providers (config.py's
VOICE_PROVIDER, see load_settings' docstring): direct vendor calls
(Deepgram/ElevenLabs, today's default) or LiveKit Inference (same
underlying vendors, billed/authenticated through LiveKit Cloud instead —
no separate provider keys needed). Both stay available; this is a runtime
switch, not a migration.

TTS pacing: ElevenLabs' default playback speed reads as rushed for an
interview (live feedback: "agent speaks too fast"). `settings.tts_speed`
below (ElevenLabs' own voice_settings.speed, ~1.0 default, see config.py's
VOICE_TTS_SPEED) applies the same slightly-slower pace to both provider
paths, so behavior doesn't silently differ between VOICE_PROVIDER=direct
and =livekit_inference.

Turn handling: endpointing (how long to wait after the candidate stops
talking before treating their turn as complete) and interruption handling
were previously left at whatever AgentSession's own defaults are —
inherited silently rather than chosen deliberately. `settings.endpointing_*`
and `settings.interruptions_enabled` (config.py) make these explicit and
independently tunable per environment; their defaults match what the
framework already did, so this is not a behavior change on its own.
`settings.turn_detection_mode` additionally swaps in LiveKit Cloud's
semantic `inference.TurnDetector()` in place of the plain silence-duration
heuristic when set to "semantic" — still bounded by the same endpointing
min/max delays, just a smarter decision within them.

STT/TTS model selection + fallback (LIVEKIT_INFERENCE only): primary and
fallback models come from `config/voice_tuning.yaml` (see
voice_tuning_config.py), not hardcoded here — `settings.stt_model`/
`tts_model` build the primary `inference.STT`/`inference.TTS` instance;
`settings.stt_fallback_models`/`tts_fallback_models` (0 or more) each
become an `inference.STT.from_model_string`/`inference.TTS.from_model_string`
instance, wrapped together with the primary in `stt.FallbackAdapter`/
`tts.FallbackAdapter` when non-empty — client-side fallback across
independently constructed instances, not LiveKit Cloud Inference's own
server-side `fallback=` model-string parameter (equally valid; this form
was chosen to match the project's reference fallback pattern and because
it composes with any STT/TTS instance, not just inference model strings).
Not applicable to the DIRECT (raw Deepgram/ElevenLabs) path, which doesn't
have a fallback tier configured — kept as a documented non-Cloud emergency
path, not the primary one now that the deployment target is LiveKit Cloud
(see .env's LiveKit Cloud URL/key/secret).

Noise cancellation (`settings.noise_cancellation_enabled`): BVC background-
voice-cancellation applied to the candidate's inbound audio track via
RoomOptions, independent of the STT/TTS provider choice above. Imported
lazily inside `build_room_options()` so the DIRECT/self-hosted path doesn't
require the (large, ~73MB) `livekit-plugins-noise-cancellation` dependency
to be installed if the toggle is left off.

VAD prewarming: `worker.py`'s `AgentServer.setup_fnc` loads Silero VAD once
per idle process (see `worker.py`'s `_prewarm`) instead of this module
reloading it on every single job dispatch — passed in via `ctx.proc.userdata`
rather than each builder calling `silero.VAD.load()` itself.
"""

import os
from typing import Any

from livekit.agents import Agent, AgentSession, inference, room_io, text_transforms
from livekit.agents import stt as stt_module
from livekit.agents import tts as tts_module
from livekit.agents.vad import VAD
from livekit.plugins import deepgram, elevenlabs

from .config import DIRECT, VOICE_TURN_DETECTION_SEMANTIC, VoiceAgentSettings, load_settings
from .conversation_start import OpeningAgent
from .discovery_llm import DiscoveryLLM
from .gateway_llm import GatewayLLM

# Spoken-text cleanup applied to every agent reply — LLM output occasionally
# contains markdown/emoji artifacts that read badly spoken verbatim; the
# replace map is also where brand-term pronunciation gets corrected.
_TTS_TEXT_TRANSFORMS = [
    "filter_markdown",
    "filter_emoji",
    text_transforms.replace({"HireOS": "Hire O S"}),
]


def _tts_voice_settings(settings: VoiceAgentSettings) -> dict:
    # ElevenLabs' own playback-rate control (~1.0 is that voice's normal
    # pace). Slightly below 1.0 reads as a more natural, less rushed
    # speaking pace for an interview — see this file's module docstring.
    return {"stability": 0.5, "similarity_boost": 0.75, "speed": settings.tts_speed}


def _turn_handling(settings: VoiceAgentSettings) -> dict:
    turn_handling: dict = {
        "endpointing": {
            "min_delay": settings.endpointing_min_delay_s,
            "max_delay": settings.endpointing_max_delay_s,
        },
        "interruption": {"enabled": settings.interruptions_enabled},
    }
    if settings.turn_detection_mode == VOICE_TURN_DETECTION_SEMANTIC:
        turn_handling["turn_detection"] = inference.TurnDetector()
    return turn_handling


def _build_stt_tts(
    settings: VoiceAgentSettings,
) -> tuple[stt_module.STT, tts_module.TTS]:
    # language="multi" (not detect_language=True — Deepgram rejects that in
    # streaming mode, which is what a realtime voice agent always uses) lets
    # the speaker use any Deepgram-supported language, with code-switching.
    # The agent's replies stay English regardless (see each persona's system
    # prompt) — this is intentionally one-directional, not full bilingual
    # conversation.
    voice_settings = _tts_voice_settings(settings)
    if settings.voice_provider == DIRECT:
        stt_kwargs: dict[str, Any] = {"extra_kwargs": {"diarize": True}}
        if settings.stt_language:
            stt_kwargs["language"] = settings.stt_language
        stt_client = deepgram.STT(
            api_key=settings.deepgram_api_key, **stt_kwargs
        )
        tts_client = elevenlabs.TTS(
            api_key=settings.elevenlabs_api_key,
            model="eleven_flash_v2_5",
            voice_settings=elevenlabs.VoiceSettings(**voice_settings),
        )
    else:
        stt_kwargs: dict[str, Any] = {}
        if settings.stt_language:
            stt_kwargs["language"] = settings.stt_language
        primary_stt = inference.STT(
            model=settings.stt_model, **stt_kwargs
        )
        if settings.stt_fallback_models:
            stt_client = stt_module.FallbackAdapter(
                [primary_stt]
                + [inference.STT.from_model_string(m) for m in settings.stt_fallback_models]
            )
        else:
            stt_client = primary_stt

        extra_kwargs = {}
        if settings.tts_model.startswith("elevenlabs/"):
            extra_kwargs["voice_settings"] = voice_settings
        elif settings.tts_model.startswith("cartesia/"):
            extra_kwargs["voice"] = os.environ.get(
                "CARTESIA_VOICE_ID", "79a125e8-cd45-4c13-8a67-188112f4dd22"
            )
        primary_tts = inference.TTS(model=settings.tts_model, extra_kwargs=extra_kwargs)
        if settings.tts_fallback_models:
            tts_client = tts_module.FallbackAdapter(
                [primary_tts]
                + [inference.TTS.from_model_string(m) for m in settings.tts_fallback_models]
            )
        else:
            tts_client = primary_tts
    return stt_client, tts_client


def build_room_options(settings: VoiceAgentSettings | None = None) -> room_io.RoomOptions:
    """Passed to AgentSession.start(room_options=...) — see worker.py.
    Currently just the noise-cancellation toggle; kept as its own function
    since RoomOptions is a session.start()-time concern, not an
    AgentSession-construction-time one."""
    settings = settings or load_settings()
    if not settings.noise_cancellation_enabled:
        return room_io.RoomOptions()
    from livekit.plugins import noise_cancellation  # lazy: optional, large dependency

    return room_io.RoomOptions(
        audio_input=room_io.AudioInputOptions(noise_cancellation=noise_cancellation.BVC())
    )


def build_agent_session(
    system_prompt: str, *, session_label: str = "unknown", vad: VAD | None = None
) -> AgentSession:
    settings = load_settings()
    stt_client, tts_client = _build_stt_tts(settings)
    return AgentSession(
        vad=vad,
        stt=stt_client,
        llm=GatewayLLM(system_prompt=system_prompt, session_label=session_label),
        tts=tts_client,
        turn_handling=_turn_handling(settings),
        tts_text_transforms=_TTS_TEXT_TRANSFORMS,
    )


def build_discovery_agent_session(
    system_prompt: str, *, session_label: str = "unknown", vad: VAD | None = None
) -> AgentSession:
    settings = load_settings()
    stt_client, tts_client = _build_stt_tts(settings)
    return AgentSession(
        vad=vad,
        stt=stt_client,
        llm=DiscoveryLLM(system_prompt=system_prompt, session_label=session_label),
        tts=tts_client,
        turn_handling=_turn_handling(settings),
        tts_text_transforms=_TTS_TEXT_TRANSFORMS,
    )


def build_voice_agent(system_prompt: str, *, opening_instructions: str) -> Agent:
    return OpeningAgent(instructions=system_prompt, opening_instructions=opening_instructions)
