-- CreateTable
CREATE TABLE "interview_transcripts" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "interview_session_id" UUID NOT NULL,
    "tenant_id" UUID NOT NULL,
    "lines_json" JSONB NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "interview_transcripts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "interview_summaries" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "interview_session_id" UUID NOT NULL,
    "tenant_id" UUID NOT NULL,
    "rolling_summary_text" TEXT,
    "evaluation_json" JSONB NOT NULL,
    "prompt_versions_used_json" JSONB NOT NULL,
    "model_usage_json" JSONB NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "interview_summaries_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "interview_transcripts_interview_session_id_key" ON "interview_transcripts"("interview_session_id");

-- CreateIndex
CREATE INDEX "interview_transcripts_tenant_id_idx" ON "interview_transcripts"("tenant_id");

-- CreateIndex
CREATE UNIQUE INDEX "interview_summaries_interview_session_id_key" ON "interview_summaries"("interview_session_id");

-- CreateIndex
CREATE INDEX "interview_summaries_tenant_id_idx" ON "interview_summaries"("tenant_id");

-- AddForeignKey
ALTER TABLE "interview_transcripts" ADD CONSTRAINT "interview_transcripts_interview_session_id_fkey" FOREIGN KEY ("interview_session_id") REFERENCES "interview_sessions"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "interview_summaries" ADD CONSTRAINT "interview_summaries_interview_session_id_fkey" FOREIGN KEY ("interview_session_id") REFERENCES "interview_sessions"("id") ON DELETE CASCADE ON UPDATE CASCADE;
