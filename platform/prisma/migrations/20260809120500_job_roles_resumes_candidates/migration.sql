-- Job Role -> Resume -> Candidate pipeline. JobRole is a hiring requisition,
-- deliberately NOT named "Role" (that's the pre-existing RBAC model, table
-- "roles"). See platform/src/job-roles/ and hireOsBe's implementation plan.

-- CreateEnum
CREATE TYPE "JobRoleStatus" AS ENUM ('DRAFT', 'OPEN', 'ON_HOLD', 'CLOSED');
CREATE TYPE "JdSourceType" AS ENUM ('UPLOAD', 'PASTE');
CREATE TYPE "ExtractionStatus" AS ENUM ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED');
CREATE TYPE "ResumeStatus" AS ENUM ('UPLOADED', 'PARSING', 'PARSED', 'PARSE_FAILED', 'QUARANTINED');
CREATE TYPE "ApplicationStage" AS ENUM ('APPLIED', 'SCREENING', 'SHORTLISTED', 'INTERVIEW_SCHEDULED', 'INTERVIEWED', 'OFFER');
CREATE TYPE "ApplicationStatus" AS ENUM ('ACTIVE', 'HIRED', 'REJECTED', 'WITHDRAWN');
CREATE TYPE "CandidateSource" AS ENUM ('RESUME_UPLOAD', 'MANUAL', 'REFERRAL', 'IMPORT');

-- CreateTable
-- id/FK columns are native UUID (matching every existing table's convention
-- from 20260724120000_auth_rbac, e.g. tenants.id) rather than TEXT — a plain
-- migrate-diff-from-schema.prisma would suggest TEXT (Prisma's `String`
-- scalar has no native pg type opinion without @db.Uuid), but the actual
-- database already uses UUID everywhere, and mixed types break FK creation.
CREATE TABLE "job_roles" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "tenant_id" UUID NOT NULL,
    "title" TEXT NOT NULL,
    "department" TEXT,
    "location" TEXT,
    "employment_type" TEXT,
    "seniority" TEXT,
    "status" "JobRoleStatus" NOT NULL DEFAULT 'DRAFT',
    "jd_source_type" "JdSourceType" NOT NULL,
    "jd_text" TEXT,
    "jd_file_key" TEXT,
    "jd_file_name" TEXT,
    "jd_mime_type" TEXT,
    "jd_size_bytes" INTEGER,
    "active_extraction_id" UUID,
    "created_by" UUID NOT NULL,
    "closed_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "job_roles_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "job_role_extractions" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "tenant_id" UUID NOT NULL,
    "job_role_id" UUID NOT NULL,
    "attempt" INTEGER NOT NULL DEFAULT 1,
    "status" "ExtractionStatus" NOT NULL DEFAULT 'PENDING',
    "extraction_json" JSONB,
    "model_version" TEXT,
    "error_code" TEXT,
    "error_message" TEXT,
    "started_at" TIMESTAMP(3),
    "completed_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "job_role_extractions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "candidates" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "tenant_id" UUID NOT NULL,
    "full_name" TEXT NOT NULL,
    "primary_email" TEXT,
    "email_normalized" TEXT,
    "primary_phone" TEXT,
    "current_title" TEXT,
    "location" TEXT,
    "source" "CandidateSource" NOT NULL DEFAULT 'RESUME_UPLOAD',
    "created_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "candidates_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "resumes" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "tenant_id" UUID NOT NULL,
    "candidate_id" UUID,
    "job_role_id" UUID,
    "uploaded_by" TEXT NOT NULL,
    "storage_key" TEXT NOT NULL,
    "original_filename" TEXT NOT NULL,
    "mime_type" TEXT NOT NULL,
    "size_bytes" INTEGER NOT NULL,
    "checksum_sha256" TEXT NOT NULL,
    "status" "ResumeStatus" NOT NULL DEFAULT 'UPLOADED',
    "extracted_text_length" INTEGER,
    "active_extraction_id" UUID,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,
    "deleted_at" TIMESTAMP(3),

    CONSTRAINT "resumes_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "resume_extractions" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "tenant_id" UUID NOT NULL,
    "resume_id" UUID NOT NULL,
    "attempt" INTEGER NOT NULL DEFAULT 1,
    "status" "ExtractionStatus" NOT NULL DEFAULT 'PENDING',
    "extraction_json" JSONB,
    "model_version" TEXT,
    "error_code" TEXT,
    "error_message" TEXT,
    "started_at" TIMESTAMP(3),
    "completed_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "resume_extractions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "applications" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "tenant_id" UUID NOT NULL,
    "candidate_id" UUID NOT NULL,
    "job_role_id" UUID NOT NULL,
    "resume_id" UUID,
    "stage" "ApplicationStage" NOT NULL DEFAULT 'APPLIED',
    "status" "ApplicationStatus" NOT NULL DEFAULT 'ACTIVE',
    "stage_entered_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "disposition_reason" TEXT,
    "assigned_to" TEXT,
    "interview_session_id" UUID,
    "created_by" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "applications_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "application_stage_events" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "tenant_id" UUID NOT NULL,
    "application_id" UUID NOT NULL,
    "from_stage" "ApplicationStage",
    "to_stage" "ApplicationStage" NOT NULL,
    "from_status" "ApplicationStatus",
    "to_status" "ApplicationStatus" NOT NULL,
    "actor_id" TEXT,
    "note" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "application_stage_events_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "job_roles_active_extraction_id_key" ON "job_roles"("active_extraction_id");
CREATE INDEX "job_roles_tenant_id_idx" ON "job_roles"("tenant_id");
CREATE INDEX "job_roles_tenant_id_status_idx" ON "job_roles"("tenant_id", "status");

CREATE INDEX "job_role_extractions_tenant_id_idx" ON "job_role_extractions"("tenant_id");
CREATE INDEX "job_role_extractions_job_role_id_status_idx" ON "job_role_extractions"("job_role_id", "status");
CREATE UNIQUE INDEX "job_role_extractions_job_role_id_attempt_key" ON "job_role_extractions"("job_role_id", "attempt");

CREATE INDEX "candidates_tenant_id_idx" ON "candidates"("tenant_id");
CREATE INDEX "candidates_tenant_id_email_normalized_idx" ON "candidates"("tenant_id", "email_normalized");

CREATE UNIQUE INDEX "resumes_storage_key_key" ON "resumes"("storage_key");
CREATE UNIQUE INDEX "resumes_active_extraction_id_key" ON "resumes"("active_extraction_id");
CREATE INDEX "resumes_tenant_id_idx" ON "resumes"("tenant_id");
CREATE INDEX "resumes_tenant_id_status_idx" ON "resumes"("tenant_id", "status");
CREATE INDEX "resumes_candidate_id_idx" ON "resumes"("candidate_id");
CREATE INDEX "resumes_tenant_id_checksum_sha256_idx" ON "resumes"("tenant_id", "checksum_sha256");
CREATE INDEX "resumes_job_role_id_idx" ON "resumes"("job_role_id");

CREATE INDEX "resume_extractions_tenant_id_idx" ON "resume_extractions"("tenant_id");
CREATE INDEX "resume_extractions_resume_id_status_idx" ON "resume_extractions"("resume_id", "status");
CREATE UNIQUE INDEX "resume_extractions_resume_id_attempt_key" ON "resume_extractions"("resume_id", "attempt");

CREATE UNIQUE INDEX "applications_interview_session_id_key" ON "applications"("interview_session_id");
CREATE INDEX "applications_tenant_id_idx" ON "applications"("tenant_id");
CREATE INDEX "applications_tenant_id_job_role_id_stage_idx" ON "applications"("tenant_id", "job_role_id", "stage");
CREATE INDEX "applications_tenant_id_status_idx" ON "applications"("tenant_id", "status");
CREATE UNIQUE INDEX "applications_tenant_id_candidate_id_job_role_id_key" ON "applications"("tenant_id", "candidate_id", "job_role_id");

CREATE INDEX "application_stage_events_tenant_id_idx" ON "application_stage_events"("tenant_id");
CREATE INDEX "application_stage_events_application_id_created_at_idx" ON "application_stage_events"("application_id", "created_at");

-- Partial unique dedupe index — not expressible in schema.prisma (no WHERE clause support).
CREATE UNIQUE INDEX "candidates_tenant_email_unique" ON "candidates" ("tenant_id", "email_normalized")
  WHERE "email_normalized" IS NOT NULL AND "deleted_at" IS NULL;

-- AddForeignKey
ALTER TABLE "job_roles" ADD CONSTRAINT "job_roles_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "job_roles" ADD CONSTRAINT "job_roles_created_by_fkey" FOREIGN KEY ("created_by") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "job_roles" ADD CONSTRAINT "job_roles_active_extraction_id_fkey" FOREIGN KEY ("active_extraction_id") REFERENCES "job_role_extractions"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "job_role_extractions" ADD CONSTRAINT "job_role_extractions_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "job_role_extractions" ADD CONSTRAINT "job_role_extractions_job_role_id_fkey" FOREIGN KEY ("job_role_id") REFERENCES "job_roles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "candidates" ADD CONSTRAINT "candidates_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "resumes" ADD CONSTRAINT "resumes_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "resumes" ADD CONSTRAINT "resumes_candidate_id_fkey" FOREIGN KEY ("candidate_id") REFERENCES "candidates"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "resumes" ADD CONSTRAINT "resumes_active_extraction_id_fkey" FOREIGN KEY ("active_extraction_id") REFERENCES "resume_extractions"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "resumes" ADD CONSTRAINT "resumes_job_role_id_fkey" FOREIGN KEY ("job_role_id") REFERENCES "job_roles"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "resume_extractions" ADD CONSTRAINT "resume_extractions_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "resume_extractions" ADD CONSTRAINT "resume_extractions_resume_id_fkey" FOREIGN KEY ("resume_id") REFERENCES "resumes"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "applications" ADD CONSTRAINT "applications_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "applications" ADD CONSTRAINT "applications_candidate_id_fkey" FOREIGN KEY ("candidate_id") REFERENCES "candidates"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "applications" ADD CONSTRAINT "applications_job_role_id_fkey" FOREIGN KEY ("job_role_id") REFERENCES "job_roles"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "applications" ADD CONSTRAINT "applications_resume_id_fkey" FOREIGN KEY ("resume_id") REFERENCES "resumes"("id") ON DELETE SET NULL ON UPDATE CASCADE;
ALTER TABLE "applications" ADD CONSTRAINT "applications_interview_session_id_fkey" FOREIGN KEY ("interview_session_id") REFERENCES "interview_sessions"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "application_stage_events" ADD CONSTRAINT "application_stage_events_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "application_stage_events" ADD CONSTRAINT "application_stage_events_application_id_fkey" FOREIGN KEY ("application_id") REFERENCES "applications"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- updated_at triggers (set_updated_at() defined in 20260724120000_auth_rbac)
CREATE TRIGGER job_roles_set_updated_at BEFORE UPDATE ON job_roles FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER candidates_set_updated_at BEFORE UPDATE ON candidates FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER resumes_set_updated_at BEFORE UPDATE ON resumes FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER applications_set_updated_at BEFORE UPDATE ON applications FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Row Level Security (defense in depth; app still filters by tenant_id — ADR-0004).
-- Newer tables have not automatically inherited RLS in this codebase, so
-- each new table gets its own explicit block.
ALTER TABLE job_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_role_extractions ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE resumes ENABLE ROW LEVEL SECURITY;
ALTER TABLE resume_extractions ENABLE ROW LEVEL SECURITY;
ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE application_stage_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_job_roles ON job_roles
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));

CREATE POLICY tenant_isolation_job_role_extractions ON job_role_extractions
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));

CREATE POLICY tenant_isolation_candidates ON candidates
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));

CREATE POLICY tenant_isolation_resumes ON resumes
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));

CREATE POLICY tenant_isolation_resume_extractions ON resume_extractions
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));

CREATE POLICY tenant_isolation_applications ON applications
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));

CREATE POLICY tenant_isolation_application_stage_events ON application_stage_events
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));

-- Permission seed — mirrors 20260728184132_add_interviews_manage_permission's
-- pattern (insert the permission, then backfill role_permissions for every
-- existing tenant's matching system role, matching SYSTEM_ROLE_PERMISSIONS
-- in src/common/permissions.ts).
INSERT INTO permissions (id, slug, module, description) VALUES
  (gen_random_uuid(), 'jobs.read', 'jobs', 'View job roles'),
  (gen_random_uuid(), 'jobs.write', 'jobs', 'Create and edit job roles'),
  (gen_random_uuid(), 'candidates.read', 'candidates', 'View candidates and pipeline'),
  (gen_random_uuid(), 'candidates.write', 'candidates', 'Create candidates and move pipeline stages'),
  (gen_random_uuid(), 'resumes.read', 'candidates', 'View and download resumes'),
  (gen_random_uuid(), 'resumes.upload', 'candidates', 'Upload resumes')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE p.slug IN ('jobs.read', 'jobs.write', 'candidates.read', 'candidates.write', 'resumes.read', 'resumes.upload')
  AND r.name = 'Admin'
ON CONFLICT (role_id, permission_id) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE p.slug IN ('jobs.read', 'jobs.write', 'candidates.read', 'candidates.write', 'resumes.read', 'resumes.upload')
  AND r.name = 'Recruiter'
ON CONFLICT (role_id, permission_id) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE p.slug IN ('jobs.read', 'candidates.read', 'candidates.write', 'resumes.read')
  AND r.name = 'Hiring Manager'
ON CONFLICT (role_id, permission_id) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE p.slug IN ('jobs.read', 'candidates.read')
  AND r.name = 'Auditor'
ON CONFLICT (role_id, permission_id) DO NOTHING;
