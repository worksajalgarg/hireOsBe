# 0001 — Modular monolith, not microservices, for the core hiring platform

## Status
Accepted (Sprint 1)

## Context
The technical roadmap's executive recommendation states: *"Modular monolith for jobs, candidates, workflows, RBAC and audit; a separately deployable AI service for extraction, matching, interview orchestration and evaluation. Avoid Kubernetes and service sprawl until usage proves the need."* The team is 4-5 engineers building an MVP in 12 weeks (PRD Section 12).

## Decision
`apps/platform` is a single NestJS application with internal module boundaries (`tenant`, `role-context`, `candidates`, `workflow`, `audit`, `integrations`), not separate deployable services. The only service split at MVP is the AI control plane (`services/ai-service`), because it has a genuinely different runtime profile (Python/ML ecosystem, model gateway) and a hard boundary the PRD requires (no direct provider calls from product code).

## Consequences
- Faster iteration and simpler deployment/ops for a small team; no inter-service network calls, distributed tracing overhead, or service-mesh complexity for the core platform.
- Module boundaries are enforced by code review and package structure (no cross-module Prisma access), not by network isolation — a discipline the team must maintain deliberately.
- Revisit only when a specific module's scaling or team-ownership needs outgrow the monolith (roadmap explicitly frames Kubernetes/service-sprawl as a "until usage proves the need" decision, not a permanent one).
