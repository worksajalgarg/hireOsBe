# 0005 — Model routing chains load from a YAML config file, not a database

## Status
Accepted (Sprint 4-ish, ai-service hardening pass)

## Context
`ai-service/app/model_gateway/use_case_policy.py`'s `USE_CASE_POLICIES` (which provider/model/timeout each use case's fallback chain uses) was a hardcoded Python dict literal. Changing it — e.g. reordering `voice_interview_turn`'s chain when Groq/Gemini free-tier quotas got exhausted during dev testing — meant editing Python source and restarting the worker. A narrower env-var escape hatch (`VOICE_LLM_PROVIDER_PRIORITY`, see `apply_provider_priority()`) already let ops *reorder* the 4 voice/discovery use cases' existing tiers without a code edit, but couldn't add/remove a use case or change *which* providers/models are in a chain, and didn't touch the other 5 use cases at all.

The ask: remove hardcoded provider/model/fallback-chain decisions from Python source entirely, driven instead by configuration or a database.

## Decision
Routing chains for all 9 use cases now load from `ai-service/config/model_routing.yaml` at process startup (`model_gateway/routing_config.py`'s `load_routing_config()`, called from `voice_agent/worker.py`'s `main()` and `app/main.py`'s FastAPI startup hook), populating the same `USE_CASE_POLICIES` dict the rest of the codebase already reads via `get_policy()`. The dataclasses (`ProviderChoice`, `UseCasePolicy`) and every call site (`gateway.py`, `gateway_llm.py`, `discovery_llm.py`) are unchanged — only how the dict gets populated changed.

**A database was considered and rejected for now.** ai-service has no DB infrastructure today (no ORM, no migrations, no connection pooling) and is a single long-lived worker process with no multi-replica or dynamic-per-tenant need that would require a DB's live-shared-state advantage over a git-reviewed config file. A YAML file is diffable and reviewable in a PR the same way the old Python literal was, without the operational cost of introducing DB infra to hold a routing table that changes a handful of times a sprint. Revisit this decision only if a dynamic, operator-facing admin UI for routing materializes — that's the actual trigger for needing live-shared state a file can't give you.

The worker reloads the YAML once per job dispatch (comparing file mtime, cheap when unchanged) so an edit takes effect for the *next* interview without a full process restart. True mid-interview hot-reload was rejected: mutating `USE_CASE_POLICIES` while a `run_stream()` call is in flight for a live interview is a real race (a chain read mid-mutation), and "next dispatch" is a safe, already-natural reload boundary.

`VOICE_LLM_PROVIDER_PRIORITY` (the env-var reorder layer) is kept as-is, layered on top of the YAML-loaded chains, rather than retired immediately — it's cheap to keep and matches existing operational muscle memory.

## Consequences
- Adding/removing a use case, or changing which providers/models are in a chain, is now a YAML edit + redeploy of the config file, not a Python source change + full deploy.
- `model_gateway/routing_config.py` validates the file at load time (unknown provider, empty chain, non-positive timeout, duplicate provider+model pair, a required use case missing entirely) and raises before any job is dispatched — same fail-fast standard as the rest of `voice_agent/config.py`.
- `USE_CASE_POLICIES` starts empty at import time; any code path that calls `get_policy()` before the startup load has run gets a `KeyError` — this is intentional (fail loud, not silently route nowhere), but means test suites need to populate it themselves (see `tests/conftest.py`'s autouse fixture, which loads the real `config/model_routing.yaml`).
- If a real DB-backed routing config is ever built, this ADR's file-based approach is the thing being replaced — that's a distinct, larger workstream (schema, migrations, an admin UI to actually make live-editing valuable) and shouldn't be bundled into an incremental change.
