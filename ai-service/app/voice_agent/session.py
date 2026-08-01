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
interview (live feedback: "agent speaks too fast"). `_TTS_SPEED` below
(ElevenLabs' own voice_settings.speed, ~1.0 default) applies the same
slightly-slower pace to both provider paths, so behavior doesn't silently
differ between VOICE_PROVIDER=direct and =livekit_inference.
"""

from livekit.agents import Agent, AgentSession, inference
from livekit.agents import stt as stt_module
from livekit.agents import tts as tts_module
from livekit.plugins import deepgram, elevenlabs, silero

from .config import DIRECT, load_settings
from .conversation_start import OpeningAgent
from .discovery_llm import DiscoveryLLM
from .gateway_llm import GatewayLLM

# ElevenLabs' own playback-rate control (~1.0 is that voice's normal pace).
# Slightly below 1.0 reads as a more natural, less rushed speaking pace for
# an interview — see this file's module docstring.
_TTS_SPEED = 0.9
_TTS_VOICE_SETTINGS = {"stability": 0.5, "similarity_boost": 0.75, "speed": _TTS_SPEED}


def _build_stt_tts() -> tuple[stt_module.STT, tts_module.TTS]:
    settings = load_settings()

    # language="multi" (not detect_language=True — Deepgram rejects that in
    # streaming mode, which is what a realtime voice agent always uses) lets
    # the speaker use any Deepgram-supported language, with code-switching.
    # The agent's replies stay English regardless (see each persona's system
    # prompt) — this is intentionally one-directional, not full bilingual
    # conversation.
    if settings.voice_provider == DIRECT:
        stt_client = deepgram.STT(api_key=settings.deepgram_api_key, language="multi")
        tts_client = elevenlabs.TTS(
            api_key=settings.elevenlabs_api_key,
            model="eleven_flash_v2_5",
            voice_settings=elevenlabs.VoiceSettings(**_TTS_VOICE_SETTINGS),
        )
    else:
        stt_client = inference.STT(model="deepgram/nova-3", language="multi")
        tts_client = inference.TTS(
            model="elevenlabs/eleven_flash_v2_5",
            extra_kwargs={"voice_settings": _TTS_VOICE_SETTINGS},
        )
    return stt_client, tts_client


def build_agent_session(system_prompt: str, *, session_label: str = "unknown") -> AgentSession:
    stt_client, tts_client = _build_stt_tts()
    return AgentSession(
        vad=silero.VAD.load(),
        stt=stt_client,
        llm=GatewayLLM(system_prompt=system_prompt, session_label=session_label),
        tts=tts_client,
    )


def build_discovery_agent_session(
    system_prompt: str, *, session_label: str = "unknown"
) -> AgentSession:
    stt_client, tts_client = _build_stt_tts()
    return AgentSession(
        vad=silero.VAD.load(),
        stt=stt_client,
        llm=DiscoveryLLM(system_prompt=system_prompt, session_label=session_label),
        tts=tts_client,
    )


def build_voice_agent(system_prompt: str, *, opening_instructions: str) -> Agent:
    return OpeningAgent(instructions=system_prompt, opening_instructions=opening_instructions)
