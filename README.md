# hireOsBe

Backend for the Enterprise AI Hiring Platform — split out from a former monorepo. Contains two services that deploy separately but share this repo for now:

- `platform/` — NestJS API: tenant/RBAC, users, audit, plus stub modules (role-context, candidates, workflow, integrations) awaiting further build-out.
- `ai-service/` — FastAPI AI control plane: model gateway (the only egress point to any LLM provider) and stub agent routers (role-intelligence, resume-intelligence, matching-engine, interview-orchestrator, evaluation-engine).

See the companion [hireOsFe](../hireOsFe) repo for the Next.js frontend that talks to `platform/` over HTTP, and `docs/` in this repo for the threat model, architecture decision records, and founder/business-owned dependency trackers.

## Quickstart

```bash
# 1. Local infra (Postgres+pgvector, Redis, MinIO, ElasticMQ)
docker compose -f infra/docker-compose.yml up -d

# 2. Platform (NestJS)
cd platform
npm install
cp .env.example .env
npm run db:migrate -- --name init
npm run start:dev            # http://localhost:4000

# 3. AI service (FastAPI), in another terminal
cd ai-service
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Or use the VS Code launch config: Run and Debug → **"Launch All (Backend)"** starts infra + both services together.

## Checks (what CI runs)
```bash
cd platform && npm run typecheck && npm run lint && npm run test && npm run build
cd ai-service && ruff check app tests && pytest -q
```

## Testing manually (see also hireOsFe's README for the frontend side)

```bash
# Create a tenant
curl -X POST http://localhost:4000/tenants \
  -H "content-type: application/json" -H "x-actor-id: founder-1" \
  -d '{"name":"Acme Corp","domain":"acme.example.com"}'

# AI service Swagger UI
open http://localhost:8000/docs
```

## Shared type contracts

`platform/src/common/types/` (`Tenant`, `User`, `AuditEvent`, `CandidateEvaluation`) is a **hand-maintained duplicate** of hireOsFe's `lib/types/`. If you change a shared type here, make the same change in hireOsFe — there is no automated sync between the two repos at this stage (see `docs/threat-model.md` for other accepted risks tracked the same way).
