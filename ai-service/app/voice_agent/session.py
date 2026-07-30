"""Builds the AgentSession for a dispatched interview room: Silero VAD +
Deepgram STT + ElevenLabs TTS (audio-only, no reasoning surface — see
gateway_llm.py's module docstring for why these are the one deliberate
exception to the model-gateway boundary) and the gateway-routed LLM for the
conversational turn itself.
"""

from livekit.agents import Agent, AgentSession
from livekit.plugins import deepgram, elevenlabs, silero

from .config import load_settings
from .gateway_llm import GatewayLLM
from .prompts import INTERVIEW_SYSTEM_PROMPT


def build_agent_session() -> AgentSession:
    settings = load_settings()
    return AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(api_key=settings.deepgram_api_key),
        llm=GatewayLLM(system_prompt=INTERVIEW_SYSTEM_PROMPT),
        tts=elevenlabs.TTS(api_key=settings.elevenlabs_api_key),
    )


def build_interview_agent() -> Agent:
    return Agent(instructions=INTERVIEW_SYSTEM_PROMPT)
