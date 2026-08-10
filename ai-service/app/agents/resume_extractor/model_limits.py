"""Context-window awareness for the resume extraction pipeline.

Not a real tokenizer — a `chars // 4` heuristic is deliberately used instead.
This only needs to be conservative enough to catch "this chunk plus the
schema instructions plus the output budget won't fit in this model's real
context window" *before* sending the call, rather than discovering that via
a raw provider error. An undercount just means a call that turns out fine
anyway; an overcount means splitting a chunk slightly smaller than strictly
necessary — both cheap, unlike a failed call and retry.
"""

from __future__ import annotations

_CHARS_PER_TOKEN = 4

# Conservative context windows (tokens) for models reachable through this
# gateway's LLM_MODE settings. Not exhaustive — an unlisted model falls back
# to _DEFAULT_CONTEXT_WINDOW, which is deliberately small so an unknown
# model is treated cautiously rather than optimistically.
_CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-4o-mini": 128_000,
    "gpt-4o": 128_000,
    "gpt-4.1-mini": 1_000_000,
    "gemini-2.0-flash-lite": 1_000_000,
    "gemini-1.5-flash": 1_000_000,
    "gemini-flash-latest": 1_000_000,
    "nvidia/nemotron-3-nano-30b-a3b:free": 128_000,
    "meta-llama/llama-3.3-70b-instruct": 128_000,
    "meta-llama/llama-3.3-70b-instruct:free": 128_000,
    "Qwen/Qwen2.5-3B-Instruct": 32_000,
    "Qwen/Qwen2.5-0.5B-Instruct": 32_000,
}
_DEFAULT_CONTEXT_WINDOW = 8_000
# Keep 10% headroom below the nominal window — the char/4 heuristic isn't
# exact, and providers sometimes count a few tokens of call overhead too.
_SAFETY_MARGIN = 0.9
_MIN_CHUNK_CHARS = 500


def context_window_for(model_name: str) -> int:
    return _CONTEXT_WINDOWS.get(model_name, _DEFAULT_CONTEXT_WINDOW)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def safe_chunk_chars(*, model_name: str, fixed_prompt_chars: int, max_output_tokens: int) -> int:
    """How many characters of resume text can safely go in one chunk for
    this model, after accounting for the fixed (per-call, chunk-independent)
    prompt overhead — system prompt + user prompt framing — and the output
    token budget. Never returns less than _MIN_CHUNK_CHARS: a model whose
    window genuinely can't fit even a minimal chunk should fail loudly at
    the actual call site, not silently produce a zero-size chunk here."""
    window = context_window_for(model_name)
    reserved_tokens = estimate_tokens(" " * fixed_prompt_chars) + max_output_tokens
    available_tokens = int(window * _SAFETY_MARGIN) - reserved_tokens
    available_chars = available_tokens * _CHARS_PER_TOKEN
    return max(_MIN_CHUNK_CHARS, available_chars)


def is_context_length_error(exc: BaseException) -> bool:
    """True for a provider's context-length-exceeded error specifically —
    distinguished from other failures so the caller can react by shrinking
    and retrying rather than treating it as a generic malformed-output
    error (which just triggers an equally-oversized correction attempt)."""
    text = f"{type(exc).__name__} {exc}".lower()
    markers = (
        "context_length_exceeded",
        "maximum context length",
        "context window",
        "too many tokens",
        "reduce the length",
        "prompt is too long",
    )
    return any(m in text for m in markers)
