# 0002 — All LLM provider access goes through a single model gateway

## Status
Accepted (Sprint 1)

## Context
The technical roadmap's reference architecture diagram states explicitly: *"model providers are never called directly from product modules. Every request passes through the model gateway, schema validation and a versioned use-case policy."* Provider flexibility (PRD Section 3, "Provider flexibility" principle) requires OpenAI/Claude/Gemini to be swappable without touching agent logic, and cost/quality routing (PRD Section 7.2 "AI model strategy by module") needs one place to change routing policy.

## Decision
`services/ai-service/app/model_gateway/` is the only module allowed to import a provider SDK (`openai`, `anthropic`, `google-generativeai`, etc.). Every agent (`role_intelligence`, `resume_intelligence`, `matching_engine`, `interview_orchestrator`, `evaluation_engine`) calls `model_gateway.run(use_case=...)` and never constructs a provider client itself. Routing policy per use case lives in `use_case_policy.py` as a plain, inspectable data structure — not scattered across agent code.

This boundary is enforced by an automated test (`tests/test_model_gateway_boundary.py`) that scans every Python file outside `model_gateway/` for provider-SDK imports and fails the build if one is found.

## Consequences
- Swapping or adding a provider, changing a routing decision, or adding a cost/latency guardrail happens in one place.
- Any future agent must call the gateway — a new agent that imports a provider SDK directly will fail CI, not just code review.
- The gateway itself has no real provider clients wired up yet in this Sprint 1 scaffold (`providers.py` stubs raise `NotImplementedError`) — implementing each provider integration is Sprint 2+ work, scoped per agent as it's built.
