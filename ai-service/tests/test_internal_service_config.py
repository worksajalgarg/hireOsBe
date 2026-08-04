import pytest

from app.voice_agent.config import load_settings


def _set_required_base_env(monkeypatch) -> None:
    monkeypatch.setenv("LIVEKIT_URL", "ws://localhost:7880")
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "secret")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("VOICE_PROVIDER", "livekit_inference")


def test_load_settings_requires_platform_internal_url(monkeypatch) -> None:
    _set_required_base_env(monkeypatch)
    monkeypatch.delenv("PLATFORM_INTERNAL_URL", raising=False)
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", "s3cr3t")

    with pytest.raises(RuntimeError, match="PLATFORM_INTERNAL_URL"):
        load_settings()


def test_load_settings_requires_internal_service_secret(monkeypatch) -> None:
    _set_required_base_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_INTERNAL_URL", "http://localhost:4000/api/v1")
    monkeypatch.delenv("INTERNAL_SERVICE_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="INTERNAL_SERVICE_SECRET"):
        load_settings()


def test_load_settings_succeeds_with_both_set(monkeypatch) -> None:
    _set_required_base_env(monkeypatch)
    monkeypatch.setenv("PLATFORM_INTERNAL_URL", "http://localhost:4000/api/v1")
    monkeypatch.setenv("INTERNAL_SERVICE_SECRET", "s3cr3t")

    settings = load_settings()

    assert settings.platform_internal_url == "http://localhost:4000/api/v1"
    assert settings.internal_service_secret == "s3cr3t"
