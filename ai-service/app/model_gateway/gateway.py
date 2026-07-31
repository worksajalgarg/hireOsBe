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

Fallback: every use_case_policy declares a fallback provider/model. `run()`
retries cleanly on the fallback if the primary raises. `run_stream()` can
only fall back *before* its first chunk has been yielded to the caller —
once the voice agent has started speaking a streamed response, switching
providers mid-stream would either double-speak or require buffering the
whole response (reintroducing the latency problem the streaming path exists
to avoid). A primary failure after the first chunk propagates as-is.

Metrics: every call logs which provider/model actually served it, context
size (char count — a token-count proxy; no tokenizer dependency per
provider is wired up), and latency. Streaming calls additionally log
time-to-first-token (ttft_s) separately from total latency, since ttft is
what the candidate actually perceives as "how long before the agent starts
talking" — total latency includes the whole spoken answer generating in the
background after speech has already started. Logged as structured `extra`
fields (matches worker.py's logging style) under logger name
"model_gateway.metrics" so they're easy to grep/filter out of the worker's
JSON log stream while an interview is running.
"""

import logging
import time
from collections.abc import AsyncIterator

from .metrics_log import append_metric
from .providers import Provider, get_provider_client
from .use_case_policy import UseCasePolicy, get_policy

logger = logging.getLogger("model_gateway")
metrics_logger = logging.getLogger("model_gateway.metrics")


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
    }
    metrics_logger.info("model_gateway turn completed", extra=record)
    append_metric(record)


class ModelGateway:
    async def run(self, *, use_case: str, system_prompt: str, user_prompt: str) -> str:
        policy = get_policy(use_case)
        context_chars = len(system_prompt) + len(user_prompt)
        start = time.monotonic()
        try:
            client = get_provider_client(policy.primary, policy.primary_model)
            result = await client.complete(system_prompt=system_prompt, user_prompt=user_prompt)
            _log_metrics(
                use_case=use_case, provider=policy.primary, model=policy.primary_model,
                context_chars=context_chars, latency_s=time.monotonic() - start,
                output_chars=len(result),
            )
            return result
        except Exception:
            if policy.fallback is None:
                raise
            logger.warning(
                "primary provider %s failed for use_case=%s, retrying on fallback %s",
                policy.primary.value, use_case, policy.fallback.value, exc_info=True,
            )
            fallback_start = time.monotonic()
            fallback_client = get_provider_client(policy.fallback, policy.fallback_model)
            result = await fallback_client.complete(
                system_prompt=system_prompt, user_prompt=user_prompt
            )
            _log_metrics(
                use_case=use_case, provider=policy.fallback, model=policy.fallback_model,
                context_chars=context_chars, latency_s=time.monotonic() - fallback_start,
                output_chars=len(result), used_fallback=True,
            )
            return result

    async def run_stream(
        self, *, use_case: str, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[str]:
        policy = get_policy(use_case)
        async for chunk in self._stream_with_fallback(
            use_case, policy, system_prompt=system_prompt, user_prompt=user_prompt
        ):
            yield chunk

    async def _stream_with_fallback(
        self, use_case: str, policy: UseCasePolicy, *, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[str]:
        context_chars = len(system_prompt) + len(user_prompt)
        start = time.monotonic()
        primary_client = get_provider_client(policy.primary, policy.primary_model)
        primary_stream = primary_client.stream_complete(
            system_prompt=system_prompt, user_prompt=user_prompt
        )
        try:
            first_chunk = await primary_stream.__anext__()
        except StopAsyncIteration:
            return
        except Exception:
            if policy.fallback is None:
                raise
            logger.warning(
                "primary provider %s failed before first chunk for use_case=%s, "
                "retrying on fallback %s",
                policy.primary.value, use_case, policy.fallback.value, exc_info=True,
            )
            async for chunk in self._log_stream(
                use_case, policy.fallback, policy.fallback_model, context_chars,
                get_provider_client(policy.fallback, policy.fallback_model).stream_complete(
                    system_prompt=system_prompt, user_prompt=user_prompt
                ),
                used_fallback=True,
            ):
                yield chunk
            return

        ttft = time.monotonic() - start
        output_chars = len(first_chunk)
        interrupted = True
        try:
            yield first_chunk
            async for chunk in primary_stream:
                output_chars += len(chunk)
                yield chunk
            interrupted = False
        finally:
            _log_metrics(
                use_case=use_case, provider=policy.primary, model=policy.primary_model,
                context_chars=context_chars, latency_s=time.monotonic() - start,
                output_chars=output_chars, ttft_s=ttft, interrupted=interrupted,
            )

    async def _log_stream(
        self,
        use_case: str,
        provider: Provider,
        model: str | None,
        context_chars: int,
        stream: AsyncIterator[str],
        *,
        used_fallback: bool,
    ) -> AsyncIterator[str]:
        start = time.monotonic()
        ttft: float | None = None
        output_chars = 0
        interrupted = True
        try:
            async for chunk in stream:
                if ttft is None:
                    ttft = time.monotonic() - start
                output_chars += len(chunk)
                yield chunk
            interrupted = False
        finally:
            _log_metrics(
                use_case=use_case, provider=provider, model=model,
                context_chars=context_chars, latency_s=time.monotonic() - start,
                output_chars=output_chars, ttft_s=ttft, used_fallback=used_fallback,
                interrupted=interrupted,
            )


model_gateway = ModelGateway()
