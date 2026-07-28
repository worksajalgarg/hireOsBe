-- Resume storage + extraction JSON persistence

CREATE TYPE "ResumeStatus" AS ENUM ('UPLOADED', 'EXTRACTING', 'EXTRACTED', 'FAILED', 'EDITED');

CREATE TABLE "resumes" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "tenant_id" UUID NOT NULL,
    "created_by_user_id" UUID NOT NULL,
    "original_filename" TEXT NOT NULL,
    "content_type" TEXT NOT NULL,
    "size_bytes" INTEGER NOT NULL,
    "storage_key" TEXT NOT NULL,
    "status" "ResumeStatus" NOT NULL DEFAULT 'UPLOADED',
    "extracted_json" JSONB,
    "working_json" JSONB,
    "parse_source" TEXT,
    "error_message" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "resumes_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "resumes_tenant_id_created_at_idx" ON "resumes"("tenant_id", "created_at");
CREATE INDEX "resumes_tenant_id_status_idx" ON "resumes"("tenant_id", "status");

ALTER TABLE "resumes" ADD CONSTRAINT "resumes_tenant_id_fkey"
  FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "resumes" ADD CONSTRAINT "resumes_created_by_user_id_fkey"
  FOREIGN KEY ("created_by_user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE TRIGGER resumes_set_updated_at
  BEFORE UPDATE ON resumes FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE resumes ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_resumes ON resumes
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));

INSERT INTO permissions (id, slug, module, description) VALUES
  (gen_random_uuid(), 'resumes.read', 'resumes', 'List and view resumes'),
  (gen_random_uuid(), 'resumes.write', 'resumes', 'Upload, edit, and delete resumes'),
  (gen_random_uuid(), 'resumes.extract', 'resumes', 'Run resume extraction pipeline')
ON CONFLICT (slug) DO NOTHING;
