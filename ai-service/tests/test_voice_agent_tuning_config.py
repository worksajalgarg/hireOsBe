import pytest

from app.voice_agent.config import (
    DEFAULT_ENDPOINTING_MAX_DELAY_S,
    DEFAULT_ENDPOINTING_MIN_DELAY_S,
    DEFAULT_INTERRUPTIONS_ENABLED,
    DEFAULT_TTS_SPEED,
    _parse_bool,
    _parse_positive_float,
)


def test_parse_positive_float_returns_default_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("VOICE_TTS_SPEED", raising=False)
    assert _parse_positive_float("VOICE_TTS_SPEED", DEFAULT_TTS_SPEED) == DEFAULT_TTS_SPEED


def test_parse_positive_float_parses_valid_value(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_TTS_SPEED", "1.1")
    assert _parse_positive_float("VOICE_TTS_SPEED", DEFAULT_TTS_SPEED) == 1.1


def test_parse_positive_float_rejects_non_numeric(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_TTS_SPEED", "fast")
    with pytest.raises(RuntimeError, match="must be a number"):
        _parse_positive_float("VOICE_TTS_SPEED", DEFAULT_TTS_SPEED)


def test_parse_positive_float_rejects_non_positive(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_ENDPOINTING_MIN_DELAY_S", "0")
    with pytest.raises(RuntimeError, match="must be > 0"):
        _parse_positive_float("VOICE_ENDPOINTING_MIN_DELAY_S", DEFAULT_ENDPOINTING_MIN_DELAY_S)

    monkeypatch.setenv("VOICE_ENDPOINTING_MAX_DELAY_S", "-1")
    with pytest.raises(RuntimeError, match="must be > 0"):
        _parse_positive_float("VOICE_ENDPOINTING_MAX_DELAY_S", DEFAULT_ENDPOINTING_MAX_DELAY_S)


def test_parse_bool_returns_default_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("VOICE_INTERRUPTIONS_ENABLED", raising=False)
    assert (
        _parse_bool("VOICE_INTERRUPTIONS_ENABLED", DEFAULT_INTERRUPTIONS_ENABLED)
        == DEFAULT_INTERRUPTIONS_ENABLED
    )


@pytest.mark.parametrize("raw,expected", [("true", True), ("True", True), ("1", True),
                                           ("yes", True), ("false", False), ("0", False),
                                           ("no", False)])
def test_parse_bool_parses_known_values(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv("VOICE_INTERRUPTIONS_ENABLED", raw)
    assert _parse_bool("VOICE_INTERRUPTIONS_ENABLED", True) is expected


def test_parse_bool_rejects_unknown_value(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_INTERRUPTIONS_ENABLED", "maybe")
    with pytest.raises(RuntimeError, match="must be true/false"):
        _parse_bool("VOICE_INTERRUPTIONS_ENABLED", True)
