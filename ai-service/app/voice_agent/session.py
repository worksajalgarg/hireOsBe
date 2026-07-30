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


def build_agent_session(system_prompt: str) -> AgentSession:
    settings = load_settings()

    # language="multi" (not detect_language=True — Deepgram rejects that in
    # streaming mode, which is what a realtime voice agent always uses) lets
    # the candidate speak any Deepgram-supported language, with code-
    # switching. The agent's replies stay English regardless (see
    # system_prompt) — this is intentionally one-directional, not full
    # bilingual conversation.
    if settings.voice_provider == DIRECT:
        stt = deepgram.STT(api_key=settings.deepgram_api_key, language="multi")
        tts = elevenlabs.TTS(api_key=settings.elevenlabs_api_key, model="eleven_flash_v2_5")
    else:
        stt = inference.STT(model="deepgram/nova-3", language="multi")
        tts = inference.TTS(model="elevenlabs/eleven_flash_v2_5")

    return AgentSession(
        vad=silero.VAD.load(),
        stt=stt,
        llm=GatewayLLM(system_prompt=system_prompt),
        tts=tts,
    )


def build_interview_agent(system_prompt: str) -> Agent:
    return Agent(instructions=system_prompt)
