# 0007 — pydantic-ai is not used for resume/role document extraction

## Status
Accepted (Sprint 2/3, resume_intelligence + role_intelligence document parsing)

## Context
Building resume and job-description parsing (`app/agents/resume_intelligence.py`, `role_intelligence.py`), `pydantic-ai` was a candidate library for typed, validated AI workflow output. On inspection, its only capability beyond plain `pydantic.BaseModel` schemas is its `Agent` runtime — a live wrapper around a model/provider connection (`Agent(model=OpenAIModel(...))` or similar) with its own retry and tool-calling loop.

That capability is exactly what ADR-0002 exists to forbid outside `app/model_gateway/`: "model providers are never called directly from product modules — every request passes through the model gateway." Constructing a `pydantic-ai` `Agent` in `app/agents/resume_intelligence.py` or `role_intelligence.py` would be a direct provider call in every practical sense, even though it wouldn't literally trip `tests/test_model_gateway_boundary.py` — that test's AST scan only flags imports of `openai`, `anthropic`, `google.generativeai`, and `google.genai` by prefix, not `pydantic_ai`.

Separately, `model_gateway.run_structured(use_case=..., schema=...)` already provides validated structured output — it sends the prompt to the routed provider's native JSON mode, validates the response against a caller-supplied `pydantic.BaseModel`, retries on validation failure, and falls through the use case's fallback chain — the entire value `pydantic-ai`'s structured-output mode would add for a single-shot extraction call. Nested/complex schema ergonomics (the other usual reason to reach for pydantic-ai) are already available via plain nested `pydantic.BaseModel` classes — see `app/voice_agent/evaluation_schema.py` for the existing in-repo pattern this codebase already uses for exactly that.

## Decision
`pydantic-ai` is not a dependency of this codebase. `resume_intelligence_schema.py` and `role_intelligence_schema.py` define plain nested `pydantic.BaseModel` classes, passed directly into `model_gateway.run_structured(schema=...)`, same pattern as `evaluation_schema.py`.

If a future feature genuinely needs `pydantic-ai`'s agentic/tool-calling runtime (not just structured output — something `run_structured` doesn't cover), it must live *inside* `app/model_gateway/`, wrapping the `pydantic-ai` `Agent` behind the same `ModelGateway.run*()` call surface every other provider integration uses, so it stays routed, audited, and circuit-broken like everything else. It must not be constructed ad hoc inside an agent module.

## Consequences
- No new dependency, no new attack surface for the "looks safe, isn't" class of boundary violation `pydantic-ai`'s `Agent` would represent.
- `tests/test_model_gateway_boundary.py` needs no change today, since `pydantic-ai` isn't imported anywhere. If it's ever added later, that test's AST scan should be extended to also flag any `pydantic_ai.Agent(...)` construction outside `model_gateway/`, not just import prefixes — see this ADR's Context for why the current prefix-only check wouldn't catch it.
