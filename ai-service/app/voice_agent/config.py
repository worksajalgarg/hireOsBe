"""Env-driven settings for the voice agent worker — the single source of
truth for its env vars (session.py reads keys from here, not raw os.environ).
Mirrors the LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET convention
shared with platform/ — see hireOsBe/CLAUDE.md's "Shared type contracts"
note: no shared package exists between the two runtimes, so config
conventions are kept aligned by hand.
"""

import os
from dataclasses import dataclass

DIRECT = "direct"
LIVEKIT_INFERENCE = "livekit_inference"


@dataclass(frozen=True)
class VoiceAgentSettings:
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    gemini_api_key: str
    voice_provider: str  # DIRECT or LIVEKIT_INFERENCE — see session.py
    deepgram_api_key: str  # "" when voice_provider != DIRECT
    elevenlabs_api_key: str  # "" when voice_provider != DIRECT


def load_settings() -> VoiceAgentSettings:
    """Validates the keys `session.py` actually uses so a missing credential
    fails at worker startup, not mid-call after a job has already been
    dispatched into a room. OPENAI_API_KEY is deliberately not required here
    — it's only a use_case_policy fallback (see
    model_gateway/use_case_policy.py), not on the baseline path.

    VOICE_PROVIDER=direct (default) calls Deepgram/ElevenLabs with their own
    keys, required below. VOICE_PROVIDER=livekit_inference routes STT/TTS
    through LiveKit Cloud's bundled inference instead (billed via
    LIVEKIT_API_KEY/SECRET, already required) — DEEPGRAM_API_KEY/
    ELEVENLABS_API_KEY aren't needed in that mode, so they're not required
    to be non-empty."""
    voice_provider = os.environ.get("VOICE_PROVIDER", DIRECT)
    if voice_provider == DIRECT:
        deepgram_api_key = _require("DEEPGRAM_API_KEY")
        elevenlabs_api_key = _require("ELEVENLABS_API_KEY")
    else:
        deepgram_api_key = os.environ.get("DEEPGRAM_API_KEY", "")
        elevenlabs_api_key = os.environ.get("ELEVENLABS_API_KEY", "")

    return VoiceAgentSettings(
        livekit_url=_require("LIVEKIT_URL"),
        livekit_api_key=_require("LIVEKIT_API_KEY"),
        livekit_api_secret=_require("LIVEKIT_API_SECRET"),
        gemini_api_key=_require("GEMINI_API_KEY"),
        voice_provider=voice_provider,
        deepgram_api_key=deepgram_api_key,
        elevenlabs_api_key=elevenlabs_api_key,
    )


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var {name}")
    return value
