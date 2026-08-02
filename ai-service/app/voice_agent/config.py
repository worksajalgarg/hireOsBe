"""Env-driven settings for the voice agent worker — the single source of
truth for its env vars (session.py reads keys from here, not raw os.environ).
Mirrors the LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET convention
shared with platform/ — see hireOsBe/CLAUDE.md's "Shared type contracts"
note: no shared package exists between the two runtimes, so config
conventions are kept aligned by hand.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from ..model_gateway.providers import Provider

DIRECT = "direct"
LIVEKIT_INFERENCE = "livekit_inference"

# ai-service/config/model_routing.yaml relative to this file's location
# (app/voice_agent/config.py -> app/voice_agent -> app -> ai-service).
_DEFAULT_ROUTING_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "model_routing.yaml"
)

# Voice-tuning defaults below match what was previously hardcoded/implicit —
# see session.py's module docstring for _TTS_SPEED history, and
# livekit-agents' AgentSession turn_handling defaults for the other two
# (0.5s/3.0s endpointing, interruptions enabled) — these were always in
# effect, just silently inherited from the framework rather than visible
# here. Making them env vars doesn't change default behavior; it lets ops
# tune them without a code deploy.
DEFAULT_TTS_SPEED = 0.9
DEFAULT_ENDPOINTING_MIN_DELAY_S = 0.5
DEFAULT_ENDPOINTING_MAX_DELAY_S = 3.0
DEFAULT_INTERRUPTIONS_ENABLED = True

# Live-tested default as of today's session: a free OpenRouter model first
# (Groq's daily token cap and Gemini's free-tier cap both got exhausted
# simultaneously during heavy dev testing, leaving no working provider at
# all — see use_case_policy.py's voice_interview_turn rationale). Revisit
# back to Groq-first once Groq/Gemini are on a tier where that's no longer
# a real risk — that's exactly what VOICE_LLM_PROVIDER_PRIORITY is for: an
# env-var change, not a code edit.
DEFAULT_LLM_PROVIDER_PRIORITY = [Provider.OPENROUTER, Provider.GEMINI, Provider.GROQ]


@dataclass(frozen=True)
class VoiceAgentSettings:
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    gemini_api_key: str
    voice_provider: str  # DIRECT or LIVEKIT_INFERENCE — see session.py
    deepgram_api_key: str  # "" when voice_provider != DIRECT
    elevenlabs_api_key: str  # "" when voice_provider != DIRECT
    # Which LLM provider the voice/discovery use cases try first, second,
    # third — see model_gateway/use_case_policy.py's apply_provider_priority(),
    # called once at worker startup with this value (see worker.py's main()).
    llm_provider_priority: list[Provider]
    # Path to the YAML file defining every use case's provider/model/timeout
    # chain — see model_gateway/routing_config.py's load_routing_config(),
    # called once at worker startup and reloaded per job dispatch (see
    # worker.py). Overridable via ROUTING_CONFIG_PATH for tests/alternate envs.
    routing_config_path: Path
    # ElevenLabs voice_settings.speed override — see session.py's
    # _TTS_VOICE_SETTINGS and module docstring.
    tts_speed: float
    # AgentSession turn_handling.endpointing overrides — see session.py.
    endpointing_min_delay_s: float
    endpointing_max_delay_s: float
    # AgentSession turn_handling.interruption.enabled override — see session.py.
    interruptions_enabled: bool


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
        llm_provider_priority=_parse_llm_provider_priority(),
        routing_config_path=Path(
            os.environ.get("ROUTING_CONFIG_PATH", str(_DEFAULT_ROUTING_CONFIG_PATH))
        ),
        tts_speed=_parse_positive_float("VOICE_TTS_SPEED", DEFAULT_TTS_SPEED),
        endpointing_min_delay_s=_parse_positive_float(
            "VOICE_ENDPOINTING_MIN_DELAY_S", DEFAULT_ENDPOINTING_MIN_DELAY_S
        ),
        endpointing_max_delay_s=_parse_positive_float(
            "VOICE_ENDPOINTING_MAX_DELAY_S", DEFAULT_ENDPOINTING_MAX_DELAY_S
        ),
        interruptions_enabled=_parse_bool(
            "VOICE_INTERRUPTIONS_ENABLED", DEFAULT_INTERRUPTIONS_ENABLED
        ),
    )


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var {name}")
    return value


def _parse_positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be a number, got {raw!r}") from None
    if value <= 0:
        raise RuntimeError(f"{name} must be > 0, got {value}")
    return value


def _parse_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if not raw:
        return default
    normalized = raw.strip().lower()
    if normalized in ("true", "1", "yes"):
        return True
    if normalized in ("false", "0", "no"):
        return False
    raise RuntimeError(f"{name} must be true/false, got {raw!r}")


def _parse_llm_provider_priority() -> list[Provider]:
    """VOICE_LLM_PROVIDER_PRIORITY="openrouter,gemini,groq" — comma-separated
    provider names, tried in that order for voice_interview_turn/summary and
    role_discovery_turn/extraction (see use_case_policy.py's
    apply_provider_priority(), applied once in worker.py's main()). Unset
    keeps today's live-tested default. Validated here (fail at startup, not
    mid-call) — an unknown name or a duplicate is a config mistake, not
    something to silently ignore."""
    raw = os.environ.get("VOICE_LLM_PROVIDER_PRIORITY")
    if not raw:
        return list(DEFAULT_LLM_PROVIDER_PRIORITY)

    names = [name.strip() for name in raw.split(",") if name.strip()]
    if not names:
        raise RuntimeError("VOICE_LLM_PROVIDER_PRIORITY is set but empty")

    providers: list[Provider] = []
    for name in names:
        try:
            providers.append(Provider(name))
        except ValueError:
            valid = ", ".join(p.value for p in Provider)
            raise RuntimeError(
                f"VOICE_LLM_PROVIDER_PRIORITY has unknown provider '{name}' — valid: {valid}"
            ) from None

    if len(set(providers)) != len(providers):
        raise RuntimeError(f"VOICE_LLM_PROVIDER_PRIORITY has a duplicate provider: {raw!r}")

    return providers
