from pathlib import Path

import pytest
import yaml

from app.voice_agent.voice_tuning_config import VoiceTuningConfigError, load_voice_tuning_config

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_VALID_FIXTURE = _FIXTURES_DIR / "voice_tuning_valid.yaml"
_REAL_CONFIG = Path(__file__).resolve().parent.parent / "config" / "voice_tuning.yaml"


def test_valid_file_parses_correctly() -> None:
    config = load_voice_tuning_config(_VALID_FIXTURE)

    assert config.stt_model == "deepgram/nova-3"
    assert config.stt_fallback_models == ["assemblyai/universal-streaming:en"]
    assert config.tts_model == "elevenlabs/eleven_flash_v2_5"
    assert config.tts_fallback_models == []


def test_real_config_matches_previously_hardcoded_defaults() -> None:
    """Behavior-preserving migration check — the shipped config/voice_tuning.yaml
    must resolve to exactly what session.py used to hardcode."""
    config = load_voice_tuning_config(_REAL_CONFIG)

    assert config.stt_model == "deepgram/nova-3"
    assert config.stt_fallback_models == []
    assert config.tts_model == "elevenlabs/eleven_flash_v2_5"
    assert config.tts_fallback_models == []


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(VoiceTuningConfigError, match="Could not read"):
        load_voice_tuning_config(tmp_path / "does_not_exist.yaml")


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("stt: [this is not: valid: yaml")
    with pytest.raises(VoiceTuningConfigError, match="not valid YAML"):
        load_voice_tuning_config(path)


def test_non_mapping_root_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("- just\n- a\n- list\n")
    with pytest.raises(VoiceTuningConfigError, match="must be a mapping"):
        load_voice_tuning_config(path)


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data))


def _minimal_valid_config() -> dict:
    return {
        "stt": {"model": "deepgram/nova-3", "fallback_models": []},
        "tts": {"model": "elevenlabs/eleven_flash_v2_5", "fallback_models": []},
    }


def test_empty_model_raises(tmp_path: Path) -> None:
    data = _minimal_valid_config()
    data["stt"]["model"] = ""
    path = tmp_path / "config.yaml"
    _write_yaml(path, data)
    with pytest.raises(VoiceTuningConfigError, match="must not be empty"):
        load_voice_tuning_config(path)


def test_duplicate_fallback_model_raises(tmp_path: Path) -> None:
    data = _minimal_valid_config()
    data["tts"]["fallback_models"] = ["cartesia/sonic-3", "cartesia/sonic-3"]
    path = tmp_path / "config.yaml"
    _write_yaml(path, data)
    with pytest.raises(VoiceTuningConfigError, match="duplicate"):
        load_voice_tuning_config(path)


def test_missing_stt_or_tts_section_raises(tmp_path: Path) -> None:
    data = _minimal_valid_config()
    del data["tts"]
    path = tmp_path / "config.yaml"
    _write_yaml(path, data)
    with pytest.raises(VoiceTuningConfigError):
        load_voice_tuning_config(path)


def test_unknown_top_level_key_raises(tmp_path: Path) -> None:
    data = _minimal_valid_config()
    data["unexpected"] = "value"
    path = tmp_path / "config.yaml"
    _write_yaml(path, data)
    with pytest.raises(VoiceTuningConfigError):
        load_voice_tuning_config(path)
