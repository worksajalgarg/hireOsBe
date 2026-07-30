"""Env-driven settings for the voice agent worker — the single source of
truth for its env vars (session.py reads keys from here, not raw os.environ).
Mirrors the LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET convention
shared with platform/ — see hireOsBe/CLAUDE.md's "Shared type contracts"
note: no shared package exists between the two runtimes, so config
conventions are kept aligned by hand.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceAgentSettings:
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    gemini_api_key: str
    deepgram_api_key: str
    elevenlabs_api_key: str


def load_settings() -> VoiceAgentSettings:
    """Validates the keys `session.py` actually uses (Gemini LLM, Deepgram
    STT, ElevenLabs TTS) so a missing credential fails at worker startup,
    not mid-call after a job has already been dispatched into a room.
    OPENAI_API_KEY is deliberately not required here — it's only a
    use_case_policy fallback (see model_gateway/use_case_policy.py), not on
    the baseline path."""
    return VoiceAgentSettings(
        livekit_url=_require("LIVEKIT_URL"),
        livekit_api_key=_require("LIVEKIT_API_KEY"),
        livekit_api_secret=_require("LIVEKIT_API_SECRET"),
        gemini_api_key=_require("GEMINI_API_KEY"),
        deepgram_api_key=_require("DEEPGRAM_API_KEY"),
        elevenlabs_api_key=_require("ELEVENLABS_API_KEY"),
    )


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var {name}")
    return value
