# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository scope

This is **hireOsBe** — the backend repo for the Enterprise AI Hiring Platform, split out from a former monorepo. It contains two services:
- `platform/` — NestJS API (tenant/RBAC, users, audit, plus stub modules for role-context, candidates, workflow, integrations).
- `ai-service/` — FastAPI AI control plane (model gateway + stub agent routers).

The frontend (`hireOsFe`, a sibling repo) has no backend logic of its own and talks to `platform/` over HTTP only. If a task is about rendering UI, routing, or client-side state, it belongs in `hireOsFe`, not here.

## Product summary

**Enterprise AI Hiring Platform** — an enterprise hiring intelligence platform, not a full ATS. It converts role context into structured, explainable candidate evidence using resume intelligence and an AI-led voice screening interview, while keeping final hiring authority with human reviewers.

**Product thesis**: Convert role context into structured, explainable candidate evidence using resume intelligence and an AI-led voice screening interview — while keeping final hiring authority with authorised humans.

**Explicitly NOT building**: full ATS/career site/payroll/onboarding, autonomous sourcing or rejection, video/facial/emotion/biometric inference, native integrations beyond one ATS + CSV/API/webhooks, mobile native apps, multi-region active-active deployment, proctoring/anti-cheating surveillance, model fine-tuning.

**Target segment**: India-based mid-to-senior technology, product, data, fintech and BFSI hiring. Pilot scope is 2 design partners (or one paying customer), 3–5 roles, 100–250 candidates, English-only interviews of 30–45 minutes.

## Core architectural principle

The system is split into three layers with a hard boundary between them:

1. **Experience & access** (Next.js/TypeScript, lives in the sibling `hireOsFe` repo) — recruiter portal, admin portal, candidate interview app (WebRTC/LiveKit), WAF/CDN, SSO/MFA.
2. **Core hiring platform** (`platform/` in this repo) — a **NestJS modular monolith** (deliberately not microservices/Kubernetes for MVP) handling tenant & RBAC, role context, candidates, workflow, audit & consent, integrations. Communicates via domain events + REST/async commands.
3. **AI intelligence & control** (`ai-service/` in this repo) — a separately deployable **Python/FastAPI AI service** acting as the sole model gateway. Modules: Role Intelligence, Resume Intelligence, Matching Engine, Interview Orchestrator, Evaluation Engine.

**Non-negotiable guardrail**: model providers (OpenAI/Claude/Gemini) are never called directly from product modules — every request passes through `ai-service`'s model gateway (`ai-service/app/model_gateway/`), with schema validation and a versioned use-case policy. This boundary is enforced by an automated test (`ai-service/tests/test_model_gateway_boundary.py`) that fails the build if any file outside `model_gateway/` imports a provider SDK. The AI service uses the realtime model only to *conduct* the interview; a separate offline evaluator scores it against a versioned rubric. **Final ranking is produced by a deterministic scoring engine — LLMs cannot modify weights, thresholds, or eligibility rules** (see `docs/adr/0003-deterministic-final-scoring.md`).

Data layer: PostgreSQL (+ pgvector for semantic matching, tenant RLS) as system of record via Prisma with a `pg` driver adapter (`platform/src/common/prisma.service.ts`), encrypted object storage (S3-class, MinIO locally) for resumes/audio/reports, Redis for session/cache, SQS-style async workers (ElasticMQ locally) for parsing/evaluation/reports/integrations, deterministic scoring service, and full observability (OTel/Langfuse/Sentry-class tracing, not yet implemented). Every AI decision remains human-reviewable and overridable, and is tied to an immutable audit trail (`platform/src/audit/`: rubric/model/prompt version, evidence, human action).

## AI agent boundaries (do not blur these when implementing)

Each AI "agent" (`ai-service/app/agents/*`) has a hard boundary it cannot cross — preserve this decomposition in code, don't collapse agents into one another:

| Agent | Responsibility | Cannot do |
|---|---|---|
| Role Context Agent | generate/refine success profile, criteria, evidence anchors | publish a rubric without user approval |
| Resume Evidence Agent | extract claims, timeline, evidence, verification topics | infer missing experience as fact |
| Interview Designer Agent | create common + candidate-specific questions, scoring anchors | launch unapproved questions |
| Voice Interviewer | conduct approved interview, bounded probes | change rubric/recommendation policy or access other candidates |
| Evaluation Agent | map evidence to criteria, confidence, recommendation | issue final hiring decision |
| Responsible AI Agent | grounding, prohibited-attribute, policy compliance checks | rewrite source evidence (can only block publication) |
| Quality Monitor | model/speech/latency/cost/drift signals | modify production policy without approved change |

Recommended model routing (from the technical roadmap, subject to re-pricing at implementation time — see `ai-service/app/model_gateway/use_case_policy.py`): high-volume/structured work (resume parsing, candidate report) → smaller/cheaper models; complex reasoning (role rubric generation, interview evaluation) → stronger models; realtime voice → low-latency speech model behind a provider abstraction; **final ranking → no LLM at all**, deterministic rules only. Expected mix: ~75% low-cost tier, ~22% high-reasoning tier, ~3% escalation.

## Responsible AI constraints (hard requirements, not aspirational)

These are launch-blocking acceptance criteria, not nice-to-haves — treat any code path that violates them as a bug:

- No facial, emotional, accent, age, gender, personality, honesty, or deception inference — the evaluation schema (`platform/src/common/types/evaluation.ts`) must contain no such fields.
- No autonomous rejection in MVP. AI recommendation and human decision are always stored as **separate fields**; only an authorised human can advance/reject a candidate.
- Every score must cite supporting evidence or be explicitly marked as missing/insufficient evidence — never silently converted into a fabricated conclusion.
- A failed connection, speech-recognition issue, accommodation need, or candidate complaint must **never silently lower the candidate's score** — these route to a review flag/operational queue instead.
- Model/prompt changes require evidence, approval, versioning, and rollback capability; unapproved versions cannot reach production (see `ai-service/app/registry/prompt_registry.py`).
- Tenant isolation must be enforced at application, database query, object path, cache, and audit layers — not just at the API boundary. See `platform/src/common/tenant-context.middleware.ts` and `docs/threat-model.md`.
- Do not claim the platform "removes bias," "predicts employee success," "detects honesty," or "objectively measures personality." Position strictly as structured, explainable decision support.

## This repo's docs

- `docs/threat-model.md` — STRIDE-style pass covering tenant isolation, PII handling, prompt injection, and accepted dependency risks.
- `docs/adr/` — architecture decision records (monolith-not-microservices, model-gateway-boundary, deterministic-final-scoring).
- `docs/design-partners.md`, `docs/evaluation-datasets.md` — founder/business-owned Week-1 dependencies, tracked so they aren't silently dropped.

## Shared type contracts

`platform/src/common/types/` is a **hand-maintained duplicate** of hireOsFe's `lib/types/`. If you change a shared type here (`Tenant`, `User`, `AuditEvent`, `CandidateEvaluation`), make the same change in `hireOsFe` — there is no automated sync or shared package between the two repos at this stage.

## 12-week delivery plan (reference)

Six two-week sprints, each ending with a demonstrable increment and a measurable exit criterion:

| Sprint | Weeks | Milestone |
|---|---|---|
| 1 | 1-2 | Foundation complete (repo, CI/CD, tenant model, audit foundation) — **this is what's built so far** |
| 2 | 3-4 | Core ATS workflow (role builder, scorecard editor, candidate pipeline) |
| 3 | 5-6 | Explainable shortlist (matching, review experience, rejection controls) |
| 4 | 7-8 | Interview alpha (voice UX, device checks, recovery flows) |
| 5 | 9-10 | Enterprise beta (admin, audit, retention, integration config) |
| 6 | 11-12 | Design-partner go-live (pilot feedback, usability fixes, release docs) |

Coding agents are expected to accelerate scaffolding/tests/migrations, but architecture, security decisions, AI evaluation, and candidate-facing experience stay under accountable human ownership — do not let generated code silently take over these areas.
