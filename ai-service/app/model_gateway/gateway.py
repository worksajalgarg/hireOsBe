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
from typing import TypeVar

from pydantic import BaseModel

from .metrics_log import append_metric
from .providers import Provider, get_provider_client
from .use_case_policy import ProviderChoice, UseCasePolicy, get_policy

logger = logging.getLogger("model_gateway")
metrics_logger = logging.getLogger("model_gateway.metrics")

_SchemaT = TypeVar("_SchemaT", bound=BaseModel)

# Live-observed normal range for voice_interview_turn on Groq is ~0.3-1.3s;
# 4s gives generous headroom above ordinary jitter while still catching a
# real outlier (a live 16s case prompted this) fast enough that falling
# back is still much better than the candidate sitting through it.
_FIRST_CHUNK_TIMEOUT_S = 4.0


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
) -> None:
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
    }
    metrics_logger.info("model_gateway turn completed", extra=record)
    append_metric(record)


class ModelGateway:
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
            start = time.monotonic()
            try:
                client = get_provider_client(choice.provider, choice.model)
                result = await client.complete(
                    system_prompt=system_prompt, user_prompt=user_prompt
                )
            except Exception as exc:
                last_exc = exc
                is_last = tier == len(policy.chain) - 1
                logger.warning(
                    "provider %s failed for use_case=%s (tier %d/%d)%s",
                    choice.provider.value, use_case, tier + 1, len(policy.chain),
                    "" if is_last else ", trying next tier", exc_info=True,
                )
                continue
            _log_metrics(
                use_case=use_case, provider=choice.provider, model=choice.model,
                context_chars=context_chars, latency_s=time.monotonic() - start,
                output_chars=len(result), used_fallback=tier > 0, context_detail=context_detail,
            )
            return result
        if last_exc is not None:
            raise last_exc  # every tier in the chain failed
        raise RuntimeError(f"{use_case}: no providers configured in chain")

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
        parsed, choice, latency_s, tier = await self._structured_chain(
            use_case, policy, system_prompt=system_prompt, user_prompt=user_prompt, schema=schema,
        )
        _log_metrics(
            use_case=use_case, provider=choice.provider, model=choice.model,
            context_chars=context_chars, latency_s=latency_s,
            output_chars=len(parsed.model_dump_json()), used_fallback=tier > 0,
            context_detail=context_detail,
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
    ) -> tuple[_SchemaT, ProviderChoice, float, int]:
        for tier, choice in enumerate(policy.chain):
            start = time.monotonic()
            parsed = await self._structured_attempt(
                choice.provider, choice.model, system_prompt, user_prompt, schema
            )
            if parsed is not None:
                return parsed, choice, time.monotonic() - start, tier
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
    ) -> _SchemaT | None:
        """Exactly one retry (two attempts total) per chain tier — a single
        transient malformed response shouldn't force skipping straight to
        the next (often weaker-tiered, for some use cases) provider, but
        repeated failures should."""
        client = get_provider_client(provider, model)
        for attempt in range(2):
            try:
                raw = await client.complete_json(
                    system_prompt=system_prompt, user_prompt=user_prompt
                )
                return schema.model_validate_json(raw)
            except Exception:
                logger.warning(
                    "structured output attempt %d/2 failed for provider %s",
                    attempt + 1, provider.value, exc_info=True,
                )
        return None

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
        choice = chain[tier]
        timeout_s = choice.timeout_s if choice.timeout_s is not None else _FIRST_CHUNK_TIMEOUT_S
        start = time.monotonic()
        client = get_provider_client(choice.provider, choice.model)
        stream = client.stream_complete(system_prompt=system_prompt, user_prompt=user_prompt)
        try:
            first_chunk = await asyncio.wait_for(stream.__anext__(), timeout=timeout_s)
        except StopAsyncIteration:
            return
        except Exception as exc:
            is_last = tier == len(chain) - 1
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
        interrupted = True
        try:
            yield first_chunk
            async for chunk in stream:
                output_chars += len(chunk)
                yield chunk
            interrupted = False
        finally:
            _log_metrics(
                use_case=use_case, provider=choice.provider, model=choice.model,
                context_chars=context_chars, latency_s=time.monotonic() - start,
                output_chars=output_chars, ttft_s=ttft, used_fallback=tier > 0,
                interrupted=interrupted, context_detail=context_detail,
            )


model_gateway = ModelGateway()
