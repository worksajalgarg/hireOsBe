"""Loads STT/TTS/LLM model selection from config/voice_tuning.yaml — see that
file and docs/adr/0005-config-driven-model-routing.md (the same YAML+
Pydantic+fail-fast pattern, applied here to a sibling concern). Kept
separate from model_gateway/routing_config.py's model_routing.yaml on
purpose: that file owns *LLM* routing chains for the DIRECT provider path;
this file owns STT/TTS model selection (always via LiveKit Inference) and
LLM model selection *only* when VOICE_PROVIDER=livekit_inference — see
gateway.py's set_livekit_inference_mode().

No mtime-based reload machinery needed here (unlike routing_config.py,
which populates a long-lived module-level dict) — load_voice_tuning_config()
is called fresh inside voice_agent/config.py's load_settings(), which
itself already re-runs on every job dispatch (see worker.py's entrypoint()),
so this YAML is naturally re-read every dispatch for free.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, field_validator


class VoiceTuningConfigError(RuntimeError):
    pass


class _SttTtsEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    fallback_models: list[str] = []

    @field_validator("model")
    @classmethod
    def _non_empty_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model must not be empty")
        return value

    @field_validator("fallback_models")
    @classmethod
    def _valid_fallback_models(cls, value: list[str]) -> list[str]:
        if any(not m.strip() for m in value):
            raise ValueError("fallback_models entries must not be empty")
        if len(set(value)) != len(value):
            raise ValueError(f"fallback_models has a duplicate entry: {value}")
        return value


class _LlmEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "google/gemini-2.5-flash-lite"
    fallback_models: list[str] = []

    @field_validator("model")
    @classmethod
    def _non_empty_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("llm.model must not be empty")
        return value

    @field_validator("fallback_models")
    @classmethod
    def _valid_fallback_models(cls, value: list[str]) -> list[str]:
        if any(not m.strip() for m in value):
            raise ValueError("llm.fallback_models entries must not be empty")
        if len(set(value)) != len(value):
            raise ValueError(f"llm.fallback_models has a duplicate entry: {value}")
        return value


class _VoiceTuningFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stt: _SttTtsEntry
    tts: _SttTtsEntry
    llm: _LlmEntry = _LlmEntry()  # optional — only used when VOICE_PROVIDER=livekit_inference


@dataclass(frozen=True)
class VoiceTuningConfig:
    stt_model: str
    stt_fallback_models: list[str]
    tts_model: str
    tts_fallback_models: list[str]
    # LLM model selection — only used when VOICE_PROVIDER=livekit_inference.
    # Empty string / empty list means "not configured" (DIRECT path ignores these).
    llm_model: str
    llm_fallback_models: list[str]


def load_voice_tuning_config(path: Path) -> VoiceTuningConfig:
    """Reads and validates `path` (see config/voice_tuning.yaml). Raises
    VoiceTuningConfigError with a clear message on any malformed/missing
    config — must fail at worker startup, not mid-call."""
    try:
        raw_text = path.read_text()
    except OSError as exc:
        raise VoiceTuningConfigError(f"Could not read voice tuning config at {path}: {exc}") from exc

    try:
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise VoiceTuningConfigError(f"Voice tuning config at {path} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise VoiceTuningConfigError(f"Voice tuning config at {path} must be a mapping")

    try:
        parsed = _VoiceTuningFile(**raw)
    except Exception as exc:
        raise VoiceTuningConfigError(f"Voice tuning config at {path} is invalid: {exc}") from exc

    return VoiceTuningConfig(
        stt_model=parsed.stt.model,
        stt_fallback_models=parsed.stt.fallback_models,
        tts_model=parsed.tts.model,
        tts_fallback_models=parsed.tts.fallback_models,
        llm_model=parsed.llm.model,
        llm_fallback_models=parsed.llm.fallback_models,
    )
