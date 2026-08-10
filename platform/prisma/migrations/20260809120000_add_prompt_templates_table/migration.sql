-- prompt_templates has existed in schema.prisma (and the running prompts/
-- feature) for a while, but no migration ever created it — it must have
-- been applied to existing databases via `prisma db push` at some point
-- rather than a checked-in migration. Discovered while generating the
-- job_roles_resumes_candidates migration (a clean `migrate diff` against
-- migration history alone showed prompt_templates as missing). This
-- migration is purely additive and unrelated to that feature otherwise.
--
-- id is TEXT, not UUID (unlike every other table) — confirmed against real
-- usage: prisma/seed.ts assigns arbitrary human-readable slugs directly
-- ("standard-technical-v1"), and prompts.service.ts assigns randomUUID()
-- as a plain string. Neither relies on a DB-generated default.
CREATE TABLE "prompt_templates" (
    "id" TEXT NOT NULL,
    "tenant_id" UUID NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "category" TEXT NOT NULL DEFAULT 'Technical',
    "conversation_flow" TEXT,
    "opening_instructions" TEXT,
    "silence_instructions" TEXT,
    "system_boundaries" TEXT,
    "is_default" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "prompt_templates_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "prompt_templates_tenant_id_idx" ON "prompt_templates"("tenant_id");

ALTER TABLE "prompt_templates" ADD CONSTRAINT "prompt_templates_tenant_id_fkey"
  FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "interview_sessions" ADD COLUMN "prompt_id" TEXT,
  ADD COLUMN "prompt_snapshot_json" JSONB;

ALTER TABLE "interview_sessions" ADD CONSTRAINT "interview_sessions_prompt_id_fkey"
  FOREIGN KEY ("prompt_id") REFERENCES "prompt_templates"("id") ON DELETE SET NULL ON UPDATE CASCADE;
