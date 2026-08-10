"""Unit tests for resume_extractor's context-window sizing helpers."""

from __future__ import annotations

from app.agents.resume_extractor.model_limits import (
    context_window_for,
    estimate_tokens,
    is_context_length_error,
    safe_chunk_chars,
)


def test_context_window_for_known_model_returns_its_real_window() -> None:
    assert context_window_for("gpt-4o-mini") == 128_000


def test_context_window_for_unknown_model_uses_conservative_default() -> None:
    assert context_window_for("some-brand-new-model-2027") == 8_000


def test_estimate_tokens_never_returns_zero_for_nonempty_text() -> None:
    assert estimate_tokens("hi") >= 1


def test_safe_chunk_chars_shrinks_for_a_small_context_window() -> None:
    small_model_chars = safe_chunk_chars(
        model_name="some-brand-new-model-2027",  # falls back to 8_000 window
        fixed_prompt_chars=2000,
        max_output_tokens=4096,
    )
    large_model_chars = safe_chunk_chars(
        model_name="gpt-4o-mini",  # 128_000 window
        fixed_prompt_chars=2000,
        max_output_tokens=4096,
    )
    assert small_model_chars < large_model_chars


def test_safe_chunk_chars_never_goes_below_the_floor() -> None:
    """A model whose window can't even fit the fixed overhead + output
    budget must still get a usable (if small) chunk size back — the actual
    call site is where that combination should fail loudly, not here."""
    chars = safe_chunk_chars(
        model_name="some-brand-new-model-2027",
        fixed_prompt_chars=100_000,  # deliberately larger than the window
        max_output_tokens=4096,
    )
    assert chars == 500


def test_is_context_length_error_matches_known_provider_phrasing() -> None:
    assert is_context_length_error(Exception("Error: context_length_exceeded"))
    assert is_context_length_error(Exception("maximum context length is 8192 tokens"))
    assert not is_context_length_error(Exception("rate limit exceeded"))
    assert not is_context_length_error(ValueError("Model returned invalid JSON"))
