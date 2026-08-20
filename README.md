# hireOsBe

Backend for the Enterprise AI Hiring Platform — split out from a former monorepo. Contains two services that deploy separately but share this repo for now:

- `platform/` — NestJS API: tenant/RBAC, users, audit, LiveKit interview session/token minting (`interviews/`), plus stub modules (role-context, candidates, workflow, integrations) awaiting further build-out.
- `ai-service/` — FastAPI AI control plane: model gateway (the only egress point to any LLM provider), a LiveKit Agents voice worker (`voice_agent/`, POC), and stub agent routers (role-intelligence, resume-intelligence, matching-engine, interview-orchestrator, evaluation-engine).

See the companion [hireOsFe](../hireOsFe) repo for the Next.js frontend that talks to `platform/` over HTTP, and `docs/` in this repo for the threat model, architecture decision records, and founder/business-owned dependency trackers.

## AI Server planning docs

- [AI Server design and validation basis](docs/ai-server-design-validation.md) — product-level AI Server design covering generic capabilities, boundaries, selected technical choices, and validation path.
- [AI Server Phase 1 readonly query spec](docs/ai-server-phase-1-readonly-query-spec.md) — product contract for generic readonly query capability, object resolution, evidence answers, and action previews.
- [AI Server execution implementation plan](docs/ai-server-execution-implementation-plan.md) — selected implementation approach and execution task plan for Agent Command, Platform Read/Action APIs, RAG retrieval, and confirmation flow.

## Quickstart

```bash
# 1. Local infra (Postgres+pgvector, Redis, MinIO, ElasticMQ, LiveKit server+egress)
docker compose -f infra/docker-compose.yml up -d

# 2. Platform (NestJS)
cd platform
npm install
cp .env.example .env            # includes LIVEKIT_URL/API_KEY/API_SECRET, MINIO_* dev defaults
npm run db:migrate
npm run db:seed                 # admin@hireos.local / Password123!
npm run start:dev               # http://localhost:4000  (API prefix /api/v1)
# Swagger UI: http://localhost:4000/api/docs

# 3. AI service (FastAPI), in another terminal
cd ai-service
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env            # set a real OPENAI_API_KEY to exercise STT/LLM/TTS
.venv/bin/uvicorn app.main:app --reload --port 8000
```

## LiveKit voice interview (POC)

Demonstrates `livekit-server` (self-hosted, room/WebRTC), `livekit-agents` (AI interviewer worker, STT/LLM/TTS routed through the model gateway), and `livekit-egress` (recording to MinIO) working together. Feature-scoped POC, not the full FR-501–508 candidate flow — see `hireOsFe`'s `app/candidate/interview/[inviteToken]/`.

```bash
# after step 1 above (infra) and step 2 (platform running)

# 4. Voice agent worker, in another terminal — this is the AI interviewer
cd ai-service
set -a && source .env && set +a   # needs a real OPENAI_API_KEY to actually converse
.venv/bin/python3 -m app.voice_agent.worker start

# 5. Create a session (recruiter-authed) to get a candidate invite link
TOKEN=$(curl -s -X POST http://localhost:4000/api/v1/auth/login \
  -H "content-type: application/json" \
  -d '{"email":"admin@hireos.local","password":"Password123!"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['accessToken'])")
curl -s -X POST http://localhost:4000/api/v1/interviews \
  -H "content-type: application/json" -H "authorization: Bearer $TOKEN" \
  -d '{"candidateRef":"test-candidate"}'
# -> open the returned inviteUrl in hireOsFe (npm run dev) right away —
#    LiveKit rooms have a default empty-room timeout, so join promptly
```

Recordings land in the MinIO console (`http://localhost:9001`, `platform`/`platform123`) under `interview-recordings/{tenantId}/{sessionId}/recording.mp4`. Audit trail: `GET /api/v1/audit-events` (`interview.session.*`, `interview.recording.*`).

## Auth smoke test

```bash
curl -X POST http://localhost:4000/api/v1/auth/login \
  -H "content-type: application/json" \
  -c /tmp/hireos.cookies \
  -d '{"email":"admin@hireos.local","password":"Password123!"}'
```

OpenAPI sketch: `docs/openapi/auth-rbac.yaml`. Architecture notes: `docs/adr/0004-auth-rbac-rls.md`.

## Checks (what CI runs)
```bash
cd platform && npm run typecheck && npm run lint && npm run test && npm run build
cd ai-service && ruff check app tests && pytest -q
```

## Shared type contracts

`platform/src/common/types/` (`Tenant`, `User`, `AuditEvent`, `CandidateEvaluation`, `InterviewSession`) is a **hand-maintained duplicate** of hireOsFe's `lib/types/`. If you change a shared type here, make the same change in hireOsFe — there is no automated sync between the two repos at this stage (see `docs/threat-model.md` for other accepted risks tracked the same way).
