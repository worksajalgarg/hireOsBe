# Threat Model — Sprint 1 Pass

Initial STRIDE-style pass covering the three risk areas the PRD calls out for Week 1: tenant isolation, PII handling (resumes/audio), and prompt injection. This is a starting point, not a completed review — revisit at each phase gate (Section 14 of the PRD) and before the design-partner pilot.

## Scope
`apps/platform` (NestJS core), `services/ai-service` (FastAPI AI control plane), `apps/web` (Next.js frontend), and the local data stores (Postgres, Redis, object storage).

## Tenant isolation

| Threat | STRIDE category | Mitigation (current) | Gap / follow-up |
|---|---|---|---|
| One tenant reads another tenant's data via a missing `WHERE tenantId = ...` clause | Information disclosure | Every Prisma query in `tenant`, `users`, `audit` services is explicitly scoped by `tenantId` sourced from `TenantContextService`, not the request body. | No database-level Row-Level Security (RLS) policy yet — enforcement today is application-level only. Add Postgres RLS policies once a real Postgres instance is provisioned, so a bug in application code cannot leak cross-tenant rows. |
| Client forges `tenantId`/`actorId` via headers | Spoofing | `TenantContextMiddleware` reads identity from headers today. | This is a placeholder — see `apps/platform/src/common/tenant-context.middleware.ts`. Must be replaced with server-verified session/JWT claims before any real data is stored; headers must not be trusted from an untrusted client in production. |
| Cross-tenant object storage access (resumes/audio) | Information disclosure | Not yet implemented (Sprint 3+). | Object keys must be prefixed by `tenantId` and access must go through signed URLs scoped to the requesting tenant — track as a Sprint 3 requirement alongside Candidate Intelligence. |

## PII handling (resumes, audio, transcripts)

| Threat | STRIDE category | Mitigation (planned) | Status |
|---|---|---|---|
| Resume/audio data retained indefinitely | Information disclosure | Configurable retention policy per tenant (FR-802). | Not yet implemented — Sprint 9 "Enterprise controls". |
| Audio retained longer than needed for evaluation | Information disclosure | Audio deleted by default after transcript validation unless an approved retention purpose exists (PRD Section 6.5). | Not yet implemented — depends on Sprint 6 voice runtime. |
| Uploaded resume file is malicious (malware, oversized, wrong type) | Tampering / DoS | File-type validation, size limits, malware scanning (Section 8.1 "Uploads"). | Not yet implemented — Sprint 3 (Candidate Intelligence). |

## Prompt injection (AI voice interview / evaluation)

| Threat | STRIDE category | Mitigation (planned) | Status |
|---|---|---|---|
| Candidate instructs the interviewer to reveal system prompts, change scoring policy, skip questions, or access other candidates' data | Elevation of privilege | Runtime behaviour policy (PRD Section 6.3): ignore such instructions; agent boundaries in `services/ai-service/app/agents/*` restrict what each agent can do regardless of prompt content. | Enforcement logic not yet implemented — lands with the Interview Orchestrator in Sprint 6. The module boundary (agents cannot access other candidates, cannot change rubric policy) is scaffolded now so this constraint has a clear home. |
| Model hallucinates evidence not present in resume/interview | Tampering (of decision integrity) | Second-pass grounding/policy check before publishing a report (FR-605); evaluation schema requires every score to cite `supportingEvidence` or be marked `missing` (see `packages/shared-types/src/evaluation.ts`). | Grounding check not yet implemented — Sprint 7 (Voice evaluation alpha). |

## Not yet assessed (explicitly deferred, tracked so they aren't silently dropped)
- Real AWS deployment threat surface (IAM roles, VPC boundaries, SSO/WorkOS integration) — deferred until infra is actually provisioned (out of scope for this Sprint 1 pass per the local/docker-compose decision).
- Third-party model provider data-processing terms and subprocessor list (Section 8.1 "Third parties") — a business/legal task, not engineering.

## Accepted dependency risks (tracked, not silently ignored)
- `npm audit` reports moderate/high findings in `postcss`/`sharp`, both bundled transitively inside Next.js itself. At the time of the latest dependency pass, Next 16.2.11 was the newest stable release and still ships these; there is no newer version to bump to. The CI `security-baseline` job's `npm audit` step is `continue-on-error: true` for this reason — revisit whenever Next publishes a patch release.
- `apps/web`'s ESLint is pinned to the latest 9.x line (`^9.39.5`), one major behind the rest of the repo's ESLint 10.x, because `eslint-config-next`'s bundled `eslint-plugin-react` has not yet shipped ESLint 10 support (its own latest release still declares a peer range capping at `eslint ^9.7`). Bump `apps/web`'s `eslint`/`eslint-config-next` together once that plugin catches up.
- TypeScript is pinned to the latest 6.x line (`^6.0.3`) repo-wide rather than 7.x, because the 7.x native-compiler rewrite is too new for current tooling (`ts-jest`, `typescript-eslint`, NestJS's decorator-heavy code) to rely on yet. Revisit once that ecosystem catches up.
