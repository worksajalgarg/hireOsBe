import pytest

from app.voice_agent.config import (
    DEFAULT_TURN_DETECTION_MODE,
    VOICE_TURN_DETECTION_SEMANTIC,
    VOICE_TURN_DETECTION_VAD,
    _parse_turn_detection_mode,
)


def test_returns_default_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("VOICE_TURN_DETECTION_MODE", raising=False)
    assert _parse_turn_detection_mode() == DEFAULT_TURN_DETECTION_MODE


@pytest.mark.parametrize("raw", ["vad", "VAD", " vad ", "semantic", "SEMANTIC"])
def test_accepts_known_values_case_insensitive(monkeypatch, raw) -> None:
    monkeypatch.setenv("VOICE_TURN_DETECTION_MODE", raw)
    result = _parse_turn_detection_mode()
    assert result in (VOICE_TURN_DETECTION_VAD, VOICE_TURN_DETECTION_SEMANTIC)


def test_rejects_unknown_value(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_TURN_DETECTION_MODE", "auto")
    with pytest.raises(RuntimeError, match="must be one of"):
        _parse_turn_detection_mode()
