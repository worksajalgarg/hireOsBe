import pytest

from app.model_gateway.providers import Provider
from app.voice_agent.config import DEFAULT_LLM_PROVIDER_PRIORITY, _parse_llm_provider_priority


def test_unset_env_var_returns_default(monkeypatch) -> None:
    monkeypatch.delenv("VOICE_LLM_PROVIDER_PRIORITY", raising=False)
    assert _parse_llm_provider_priority() == DEFAULT_LLM_PROVIDER_PRIORITY


def test_valid_order_parses_correctly(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_LLM_PROVIDER_PRIORITY", "groq,gemini,openrouter")
    assert _parse_llm_provider_priority() == [Provider.GROQ, Provider.GEMINI, Provider.OPENROUTER]


def test_whitespace_around_names_is_tolerated(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_LLM_PROVIDER_PRIORITY", " groq , gemini ")
    assert _parse_llm_provider_priority() == [Provider.GROQ, Provider.GEMINI]


def test_unknown_provider_name_raises(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_LLM_PROVIDER_PRIORITY", "groq,bogus")
    with pytest.raises(RuntimeError, match="unknown provider 'bogus'"):
        _parse_llm_provider_priority()


def test_duplicate_provider_raises(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_LLM_PROVIDER_PRIORITY", "groq,gemini,groq")
    with pytest.raises(RuntimeError, match="duplicate provider"):
        _parse_llm_provider_priority()


def test_empty_string_raises(monkeypatch) -> None:
    monkeypatch.setenv("VOICE_LLM_PROVIDER_PRIORITY", "   ")
    with pytest.raises(RuntimeError, match="set but empty"):
        _parse_llm_provider_priority()
