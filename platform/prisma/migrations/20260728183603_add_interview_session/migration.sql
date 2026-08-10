-- CreateEnum
CREATE TYPE "InterviewSessionStatus" AS ENUM ('PENDING', 'ACTIVE', 'COMPLETED', 'FAILED');

-- CreateTable
CREATE TABLE "interview_sessions" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "tenant_id" UUID NOT NULL,
    "candidate_ref" TEXT NOT NULL,
    "room_name" TEXT NOT NULL,
    "invite_token_hash" TEXT NOT NULL,
    "invite_expires_at" TIMESTAMP(3) NOT NULL,
    "status" "InterviewSessionStatus" NOT NULL DEFAULT 'PENDING',
    "egress_id" TEXT,
    "recording_url" TEXT,
    "started_at" TIMESTAMP(3),
    "ended_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "interview_sessions_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "interview_sessions_room_name_key" ON "interview_sessions"("room_name");

-- CreateIndex
CREATE INDEX "interview_sessions_tenant_id_idx" ON "interview_sessions"("tenant_id");

-- CreateIndex
CREATE INDEX "interview_sessions_invite_token_hash_idx" ON "interview_sessions"("invite_token_hash");

-- AddForeignKey
ALTER TABLE "interview_sessions" ADD CONSTRAINT "interview_sessions_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- Trigger
CREATE TRIGGER interview_sessions_set_updated_at
  BEFORE UPDATE ON interview_sessions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
