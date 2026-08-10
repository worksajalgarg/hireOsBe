"""
The model gateway is the sole path from any agent module to an LLM provider.
Agents call `ModelGateway.run(use_case=..., ...)`; they never construct a
provider client themselves. This is the CTO guardrail from the technical
roadmap's reference architecture diagram: "model providers are never called
directly from product modules."

Context caching investigated (not implemented) for voice_interview_turn:
Gemini's explicit context-caching API has a minimum cacheable-content size
(historically ~32k tokens) far above this use case's system prompt (~1k
tokens even with a full resume attached — see voice_agent/prompts.py's
compaction). Caching would add real lifecycle complexity (per-session cache
object, expiry, invalidation) for no benefit at this size. Revisit only if
a future system prompt (e.g. a full real job description) grows into that
range — see voice_agent/gateway_llm.py's transcript trimming for the actual
latency fix at current scale.

Fallback: each use_case_policy declares an ordered *chain* of providers
(see use_case_policy.py's UseCasePolicy.chain), not just one fallback.
`run()` walks the chain, trying the next entry on any failure. `run_stream()`
can only fall back *before* its first chunk has been yielded to the caller —
once the voice agent has started speaking a streamed response, switching
providers mid-stream would either double-speak or require buffering the
whole response (reintroducing the latency problem the streaming path exists
to avoid). A failure after the first chunk propagates as-is, from whichever
tier was serving at that point.

Fallback also triggers on a *slow* first chunk, not just a raised
exception: a provider call that eventually succeeds but takes far longer
than normal (observed live: a Groq call that took 16s to first token vs.
~0.3-1s normally, with no error at all) would otherwise sail straight past
every check above, since nothing ever raised. `_FIRST_CHUNK_TIMEOUT_S`
bounds how long each tier is allowed to take before moving to the next —
chosen well above normal variance so it doesn't false-trigger on ordinary
jitter, but far below "the candidate notices something is wrong."

Metrics: every call logs which provider/model actually served it (including
which tier of the chain), context size (char count — a token-count proxy;
no tokenizer dependency per provider is wired up), and latency. Streaming
calls additionally log time-to-first-token (ttft_s) separately from total
latency, since ttft is what the candidate actually perceives as "how long
before the agent starts talking." Logged as structured `extra` fields
(matches worker.py's logging style) under logger name
"model_gateway.metrics" so they're easy to grep/filter out of the worker's
JSON log stream while an interview is running.

`context_detail`: an optional opaque dict a caller can attach to a call,
merged verbatim into the metrics record. This module deliberately doesn't
interpret it — voice_agent/gateway_llm.py uses it to attach the actual
recent-window lines + rolling summary it sent, so the dev dashboard can show
what a turn's context really was, not just its size. Any future caller can
attach its own shape without this file needing to know about it.

`run_structured()`: for callers that need a validated, typed result (not
just text) — e.g. voice_agent/discovery_llm.py's per-turn structured-field
extraction. Prompting a model to "return JSON" and parsing raw text is
fragile on its own, so this asks the provider for its native JSON-mode
output (see providers.py's complete_json) *and* validates the result
against a caller-supplied pydantic schema, retrying once per chain tier
before moving to the next (same chain-walking shape as run()/run_stream(),
just with validation as an additional failure mode alongside a raised
exception). Raises if every tier in the chain fails — callers are expected
to treat that as a no-op for this turn (keep prior state) rather than let a
bad extraction corrupt anything, exactly like gateway_llm.py's existing
best-effort consolidation.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

from app.config import get_settings

from .circuit_breaker import circuit_breaker
from .metrics_log import append_metric, is_dev_metrics_enabled
from .providers import (
    MockProviderClient,
    Provider,
    get_provider_client,
    is_llm_quota_error,
)
from .use_case_policy import ProviderChoice, UseCasePolicy, get_policy

logger = logging.getLogger("model_gateway")
metrics_logger = logging.getLogger("model_gateway.metrics")

_SchemaT = TypeVar("_SchemaT", bound=BaseModel)

# Live-observed normal range for voice_interview_turn on Groq is ~0.3-1.3s;
# 4s gives generous headroom above ordinary jitter while still catching a
# real outlier (a live 16s case prompted this) fast enough that falling
# back is still much better than the candidate sitting through it.
_FIRST_CHUNK_TIMEOUT_S = 4.0

# Voice use cases whose chain is replaced when set_livekit_inference_mode()
# is called (see below and worker.py). Offline use cases (resume_parsing,
# interview_evaluation, etc.) keep their model_routing.yaml chains unchanged.
_VOICE_LLM_USE_CASES = [
    "voice_interview_turn",
    "voice_interview_summary",
    "role_discovery_turn",
    "role_discovery_extraction",
]


def _log_metrics(
    *,
    use_case: str,
    provider: Provider,
    model: str | None,
    context_chars: int,
    latency_s: float,
    output_chars: int,
    ttft_s: float | None = None,
    used_fallback: bool = False,
    interrupted: bool = False,
    context_detail: dict | None = None,
    retries_used: int | None = None,
    system_prompt: str | None = None,
    user_prompt: str | None = None,
    output_text: str | None = None,
) -> None:
    if is_dev_metrics_enabled():
        ctx = dict(context_detail) if context_detail else {}
        if system_prompt is not None and "system_prompt" not in ctx:
            ctx["system_prompt"] = system_prompt
        if user_prompt is not None and "user_prompt" not in ctx:
            ctx["user_prompt"] = user_prompt
        if output_text is not None and "output_text" not in ctx:
            ctx["output_text"] = output_text
        context_detail = ctx if ctx else None

    record = {
        "use_case": use_case,
        "provider": provider.value,
        "model": model,
        "context_chars": context_chars,
        "approx_context_tokens": context_chars // 4,
        "output_chars": output_chars,
        "latency_s": round(latency_s, 3),
        "ttft_s": round(ttft_s, 3) if ttft_s is not None else None,
        "used_fallback": used_fallback,
        "interrupted": interrupted,
        "context_detail": context_detail,
        # run_structured only: how many of _structured_attempt's 2 tries on
        # the *winning* tier were needed (0 = succeeded first try). A
        # provider whose JSON-mode reliability degrades but still succeeds
        # on retry was previously invisible here — only a warning log line.
        "retries_used": retries_used,
    }
    metrics_logger.info("model_gateway turn completed", extra=record)
    append_metric(record)


def _handle_provider_exc(exc: Exception, provider: Provider) -> None:
    """Classify an exception and update the circuit breaker accordingly.
    Called whenever a provider call raises in run(), run_stream(), or
    _structured_attempt() so the breaker state stays consistent across all
    three call paths."""
    try:
        # openai package may not be imported in all environments;
        # check the class name as a safe fallback.
        from openai import RateLimitError
        if isinstance(exc, RateLimitError):
            circuit_breaker.record_rate_limit(provider)
            return
    except ImportError:
        if type(exc).__name__ == "RateLimitError":
            circuit_breaker.record_rate_limit(provider)
            return
    if isinstance(exc, KeyError):
        # Missing API key — provider is structurally unavailable; give it a
        # full rate-limit cooldown so we don't retry it on every single turn.
        circuit_breaker.record_rate_limit(provider)
        return
    circuit_breaker.record_failure(provider)



@dataclass(frozen=True)
class GatewayResult:
    content: str
    provider: str
    model_name: str
    fallback_used: bool


def _model_name(settings, mode: str) -> str:
    if mode == "local":
        return settings.local_llm_model
    if mode == "gemini":
        return settings.gemini_model
    if mode in ("openrouter", "openai"):
        return settings.openai_model
    return mode


def current_model_name(use_case: str) -> str:
    """Resolves which model will handle this use case for resume sizing."""
    get_settings.cache_clear()
    settings = get_settings()
    mode = (settings.llm_mode or "mock").strip().lower()
    if mode not in ("mock", "local", "gemini", "openrouter", "openai"):
        try:
            mode = get_policy(use_case).primary.value
        except Exception:
            try:
                mode = get_policy(use_case).chain[0].provider.value
            except Exception:
                pass
    return _model_name(settings, mode)


class ModelGateway:

    async def run_detailed(
        self,
        *,
        use_case: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> "GatewayResult":
        """Resume-extractor path: LLM_MODE override + optional mock fallback."""
        get_settings.cache_clear()
        settings = get_settings()
        mode = (settings.llm_mode or "mock").strip().lower()
        if mode == "mock":
            client = get_provider_client(Provider.MOCK)
            resolved = Provider.MOCK
        elif mode == "local":
            client = get_provider_client(Provider.LOCAL)
            resolved = Provider.LOCAL
        elif mode == "gemini":
            client = get_provider_client(Provider.GEMINI)
            resolved = Provider.GEMINI
        elif mode in ("openrouter", "openai"):
            client = get_provider_client(Provider.OPENAI)
            resolved = Provider.OPENAI
        else:
            policy = get_policy(use_case)
            choice = policy.chain[0]
            client = get_provider_client(choice.provider, choice.model)
            resolved = choice.provider

        try:
            content = await client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
            )
            known_modes = ("mock", "local", "gemini", "openrouter", "openai")
            mode_name = mode if mode in known_modes else resolved.value
            return GatewayResult(
                content=content,
                provider=resolved.value,
                model_name=_model_name(settings, mode_name),
                fallback_used=False,
            )
        except Exception as exc:
            allow_fallback = settings.llm_fallback_to_mock
            if mode == "mock":
                raise
            if allow_fallback and (
                is_llm_quota_error(exc)
                or mode in ("gemini", "openrouter", "openai", "local")
            ):
                mock = MockProviderClient(
                    fallback_reason=(
                        f"Mock extraction used because {mode} LLM failed "
                        f"({type(exc).__name__}: {str(exc)[:180]}). "
                        "Pipeline completed for process testing."
                    )
                )
                content = await mock.complete(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=max_tokens,
                )
                return GatewayResult(
                    content=content,
                    provider=mock.provider.value if mock.provider else "mock",
                    model_name="mock",
                    fallback_used=True,
                )
            raise

    def set_livekit_inference_mode(
        self,
        primary: str,
        fallbacks: list[str],
        timeout_s: float = 8.0,
    ) -> None:
        """Replace voice use-case chains with pure livekit_inference tiers,
        called once at worker startup when VOICE_PROVIDER=livekit_inference.

        Builds a chain: [primary, *fallbacks], all using Provider.LIVEKIT_INFERENCE,
        and overwrites the voice LLM use cases in USE_CASE_POLICIES in-place.
        Offline use cases (resume_parsing, interview_evaluation, etc.) are not
        touched — they keep their model_routing.yaml chains. This is reversible
        by calling load_routing_config() again (worker's _reload_routing_config_if_changed).
        """
        from .use_case_policy import USE_CASE_POLICIES, UseCasePolicy
        models = [primary] + list(fallbacks)
        chain = [
            ProviderChoice(
                provider=Provider.LIVEKIT_INFERENCE,
                model=m,
                timeout_s=timeout_s,
            )
            for m in models
        ]
        rationale = (
            f"livekit_inference mode: primary={primary}, "
            f"fallbacks={fallbacks} (set by set_livekit_inference_mode)"
        )
        for use_case in _VOICE_LLM_USE_CASES:
            if use_case in USE_CASE_POLICIES:
                USE_CASE_POLICIES[use_case] = UseCasePolicy(chain=chain, rationale=rationale)
        logger.info(
            "model_gateway: livekit_inference mode active for voice use cases, "
            "chain=%s",
            [m for m in models],
        )

    async def run(
        self,
        *,
        use_case: str,
        system_prompt: str,
        user_prompt: str,
        context_detail: dict | None = None,
    ) -> str:
        policy = get_policy(use_case)
        context_chars = len(system_prompt) + len(user_prompt)
        last_exc: Exception | None = None
        for tier, choice in enumerate(policy.chain):
            # Skip providers currently in circuit-breaker cooldown.
            if not circuit_breaker.is_available(choice.provider):
                remaining = circuit_breaker.cooldown_remaining(choice.provider)
                logger.debug(
                    "circuit_breaker: skipping %s for use_case=%s (%.0fs cooldown remaining)",
                    choice.provider.value, use_case, remaining,
                )
                continue
            start = time.monotonic()
            try:
                client = get_provider_client(choice.provider, choice.model)
                result = await client.complete(
                    system_prompt=system_prompt, user_prompt=user_prompt
                )
            except Exception as exc:
                last_exc = exc
                _handle_provider_exc(exc, choice.provider)
                is_last = tier == len(policy.chain) - 1
                logger.warning(
                    "provider %s failed for use_case=%s (tier %d/%d)%s",
                    choice.provider.value, use_case, tier + 1, len(policy.chain),
                    "" if is_last else ", trying next tier", exc_info=True,
                )
                continue
            circuit_breaker.record_success(choice.provider)
            _log_metrics(
                use_case=use_case, provider=choice.provider, model=choice.model,
                context_chars=context_chars, latency_s=time.monotonic() - start,
                output_chars=len(result), used_fallback=tier > 0, context_detail=context_detail,
                system_prompt=system_prompt, user_prompt=user_prompt, output_text=result,
            )
            return result
        if last_exc is not None:
            raise last_exc  # every tier in the chain failed
        raise RuntimeError(f"{use_case}: no providers configured or all in cooldown")

    async def run_structured(
        self,
        *,
        use_case: str,
        system_prompt: str,
        user_prompt: str,
        schema: type[_SchemaT],
        context_detail: dict | None = None,
    ) -> _SchemaT:
        policy = get_policy(use_case)
        context_chars = len(system_prompt) + len(user_prompt)
        parsed, choice, latency_s, tier, retries_used = await self._structured_chain(
            use_case, policy, system_prompt=system_prompt, user_prompt=user_prompt, schema=schema,
        )
        _log_metrics(
            use_case=use_case, provider=choice.provider, model=choice.model,
            context_chars=context_chars, latency_s=latency_s,
            output_chars=len(parsed.model_dump_json()), used_fallback=tier > 0,
            context_detail=context_detail, retries_used=retries_used,
            system_prompt=system_prompt, user_prompt=user_prompt,
            output_text=parsed.model_dump_json(),
        )
        return parsed

    async def _structured_chain(
        self,
        use_case: str,
        policy: UseCasePolicy,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[_SchemaT],
    ) -> tuple[_SchemaT, ProviderChoice, float, int, int]:
        for tier, choice in enumerate(policy.chain):
            start = time.monotonic()
            parsed, retries_used = await self._structured_attempt(
                choice.provider, choice.model, system_prompt, user_prompt, schema
            )
            if parsed is not None:
                return parsed, choice, time.monotonic() - start, tier, retries_used
            is_last = tier == len(policy.chain) - 1
            if not is_last:
                logger.warning(
                    "provider %s produced no valid structured output for use_case=%s "
                    "(tier %d/%d), trying next tier",
                    choice.provider.value, use_case, tier + 1, len(policy.chain),
                )
        raise RuntimeError(
            f"{use_case}: structured output failed on every provider in the chain "
            f"({[c.provider.value for c in policy.chain]})"
        )

    async def _structured_attempt(
        self,
        provider: Provider,
        model: str | None,
        system_prompt: str,
        user_prompt: str,
        schema: type[_SchemaT],
    ) -> tuple[_SchemaT | None, int]:
        """Exactly one retry (two attempts total) per chain tier — a single
        transient malformed response shouldn't force skipping straight to
        the next (often weaker-tiered, for some use cases) provider, but
        repeated failures should. Returns (result, retries_used) so a
        success on attempt 2 — a provider whose JSON-mode reliability is
        degrading — is visible in metrics, not just a warning log line."""
        if not circuit_breaker.is_available(provider):
            return None, 0
        try:
            client = get_provider_client(provider, model)
        except (KeyError, Exception) as exc:
            _handle_provider_exc(exc, provider)
            return None, 0
        for attempt in range(2):
            try:
                raw = await client.complete_json(
                    system_prompt=system_prompt, user_prompt=user_prompt
                )
                result = schema.model_validate_json(raw)
                circuit_breaker.record_success(provider)
                return result, attempt
            except Exception:
                logger.warning(
                    "structured output attempt %d/2 failed for provider %s",
                    attempt + 1, provider.value, exc_info=True,
                )
        circuit_breaker.record_failure(provider)
        return None, 0

    async def run_stream(
        self,
        *,
        use_case: str,
        system_prompt: str,
        user_prompt: str,
        context_detail: dict | None = None,
    ) -> AsyncIterator[str]:
        policy = get_policy(use_case)
        context_chars = len(system_prompt) + len(user_prompt)
        async for chunk in self._stream_chain(
            use_case, policy.chain, 0,
            system_prompt=system_prompt, user_prompt=user_prompt,
            context_chars=context_chars, context_detail=context_detail,
        ):
            yield chunk

    async def _stream_chain(
        self,
        use_case: str,
        chain: list[ProviderChoice],
        tier: int,
        *,
        system_prompt: str,
        user_prompt: str,
        context_chars: int,
        context_detail: dict | None,
    ) -> AsyncIterator[str]:
        # Skip providers in circuit-breaker cooldown without making a network call.
        while tier < len(chain) and not circuit_breaker.is_available(chain[tier].provider):
            remaining = circuit_breaker.cooldown_remaining(chain[tier].provider)
            logger.debug(
                "circuit_breaker: skipping %s for use_case=%s (%.0fs cooldown remaining)",
                chain[tier].provider.value, use_case, remaining,
            )
            tier += 1
        if tier >= len(chain):
            logger.error(
                "_stream_chain: all providers in cooldown or exhausted for use_case=%s", use_case
            )
            return

        choice = chain[tier]
        timeout_s = choice.timeout_s if choice.timeout_s is not None else _FIRST_CHUNK_TIMEOUT_S
        start = time.monotonic()
        try:
            client = get_provider_client(choice.provider, choice.model)
        except (KeyError, Exception) as exc:
            _handle_provider_exc(exc, choice.provider)
            if tier + 1 < len(chain):
                logger.warning(
                    "provider %s unavailable for use_case=%s (tier %d/%d), trying next tier",
                    choice.provider.value, use_case, tier + 1, len(chain), exc_info=True,
                )
                async for chunk in self._stream_chain(
                    use_case, chain, tier + 1,
                    system_prompt=system_prompt, user_prompt=user_prompt,
                    context_chars=context_chars, context_detail=context_detail,
                ):
                    yield chunk
            return
        stream = client.stream_complete(system_prompt=system_prompt, user_prompt=user_prompt)
        try:
            first_chunk = await asyncio.wait_for(stream.__anext__(), timeout=timeout_s)
        except StopAsyncIteration:
            return
        except Exception as exc:
            is_last = tier == len(chain) - 1
            _handle_provider_exc(exc, choice.provider)
            # Abandon the slow/failed stream rather than leaving it running
            # in the background — best-effort, a provider client that
            # doesn't support aclose() just gets garbage collected.
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:
                    pass
            if is_last:
                raise
            is_timeout = isinstance(exc, asyncio.TimeoutError)
            logger.warning(
                "provider %s %s for use_case=%s (tier %d/%d), trying next tier",
                choice.provider.value,
                f"exceeded {timeout_s}s to first chunk" if is_timeout else "failed",
                use_case, tier + 1, len(chain), exc_info=not is_timeout,
            )
            async for chunk in self._stream_chain(
                use_case, chain, tier + 1,
                system_prompt=system_prompt, user_prompt=user_prompt,
                context_chars=context_chars, context_detail=context_detail,
            ):
                yield chunk
            return

        ttft = time.monotonic() - start
        output_chars = len(first_chunk)
        stream_chunks = [first_chunk]
        interrupted = True
        try:
            yield first_chunk
            async for chunk in stream:
                output_chars += len(chunk)
                stream_chunks.append(chunk)
                yield chunk
            interrupted = False
        finally:
            if not interrupted:
                circuit_breaker.record_success(choice.provider)
            _log_metrics(
                use_case=use_case, provider=choice.provider, model=choice.model,
                context_chars=context_chars, latency_s=time.monotonic() - start,
                output_chars=output_chars, ttft_s=ttft, used_fallback=tier > 0,
                interrupted=interrupted, context_detail=context_detail,
                system_prompt=system_prompt, user_prompt=user_prompt,
                output_text="".join(stream_chunks),
            )


model_gateway = ModelGateway()
