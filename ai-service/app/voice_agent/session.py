"""Builds the AgentSession for a dispatched interview room: Silero VAD +
STT/TTS (audio-only, no reasoning surface — see gateway_llm.py's module
docstring for why these are the one deliberate exception to the
model-gateway boundary) and the gateway-routed LLM for the conversational
turn itself.

STT/TTS come from one of two switchable providers (config.py's
VOICE_PROVIDER, see load_settings' docstring): direct vendor calls
(Deepgram/ElevenLabs, today's default) or LiveKit Inference (same
underlying vendors, billed/authenticated through LiveKit Cloud instead —
no separate provider keys needed). Both stay available; this is a runtime
switch, not a migration.
"""

from livekit.agents import Agent, AgentSession, inference
from livekit.plugins import deepgram, elevenlabs, silero

from .config import DIRECT, load_settings
from .gateway_llm import GatewayLLM
from .prompts import INTERVIEW_SYSTEM_PROMPT


def build_agent_session() -> AgentSession:
    settings = load_settings()

    # detect_language lets the candidate speak any language Deepgram
    # supports; the agent's replies stay English regardless (see
    # INTERVIEW_SYSTEM_PROMPT) — this is intentionally one-directional, not
    # full bilingual conversation.
    if settings.voice_provider == DIRECT:
        stt = deepgram.STT(api_key=settings.deepgram_api_key, detect_language=True)
        tts = elevenlabs.TTS(api_key=settings.elevenlabs_api_key, model="eleven_flash_v2_5")
    else:
        stt = inference.STT(model="deepgram/nova-3", extra_kwargs={"detect_language": True})
        tts = inference.TTS(model="elevenlabs/eleven_flash_v2_5")

    return AgentSession(
        vad=silero.VAD.load(),
        stt=stt,
        llm=GatewayLLM(system_prompt=INTERVIEW_SYSTEM_PROMPT),
        tts=tts,
    )


def build_interview_agent() -> Agent:
    return Agent(instructions=INTERVIEW_SYSTEM_PROMPT)
