import { Injectable } from "@nestjs/common";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";
import type { ResumeExtractionPayload } from "../common/types";

interface CandidateRow {
  id: string;
  fullName: string;
}

interface ApplicationRow {
  id: string;
}

@Injectable()
export class CandidateLinkingService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
  ) {}

  /** Derives a Candidate + Application from a completed resume extraction.
   * Candidate dedupe uses a raw parameterized INSERT ... ON CONFLICT (not
   * Prisma's .upsert(), which is read-or-create and not atomic) — two
   * resumes for the same person parsed in separate concurrent requests must
   * not both attempt a create and have one throw an unhandled unique
   * violation. If email is absent, always create a new Candidate — never
   * dedupe on name alone. */
  async linkFromExtraction(params: {
    tenantId: string;
    actorId: string;
    resumeId: string;
    jobRoleId?: string;
    extraction: ResumeExtractionPayload;
  }): Promise<{ candidateId: string; applicationId: string | null }> {
    const fullName = params.extraction.candidateName?.trim() || "Unknown candidate";
    const email = params.extraction.contact?.email ?? null;
    const emailNormalized = email ? email.trim().toLowerCase() : null;
    const phone = params.extraction.contact?.phone ?? null;
    const location = params.extraction.location?.trim() || null;
    // Prefer the entry explicitly marked current; fall back to the first
    // entry, since work_history is prompted to be reverse-chronological
    // (most recent role first) same as a resume itself reads.
    const currentTitle =
      (params.extraction.workHistory ?? []).find((w) => w.isCurrent)?.title ??
      params.extraction.workHistory?.[0]?.title ??
      null;

    let candidate: CandidateRow;
    let created: boolean;

    if (emailNormalized) {
      const rows = await this.prisma.$queryRaw<Array<CandidateRow & { was_inserted: boolean }>>`
        INSERT INTO candidates (id, tenant_id, full_name, primary_email, email_normalized, primary_phone, current_title, location, source, created_at, updated_at)
        VALUES (gen_random_uuid(), ${params.tenantId}::uuid, ${fullName}, ${email}, ${emailNormalized}, ${phone}, ${currentTitle}, ${location}, 'RESUME_UPLOAD', now(), now())
        ON CONFLICT (tenant_id, email_normalized) WHERE email_normalized IS NOT NULL AND deleted_at IS NULL
        DO UPDATE SET
          updated_at = now(),
          current_title = COALESCE(candidates.current_title, EXCLUDED.current_title),
          location = COALESCE(candidates.location, EXCLUDED.location)
        RETURNING id, full_name as "fullName", (xmax = 0) as was_inserted
      `;
      candidate = rows[0];
      created = rows[0].was_inserted;
    } else {
      const rows = await this.prisma.$queryRaw<CandidateRow[]>`
        INSERT INTO candidates (id, tenant_id, full_name, primary_email, primary_phone, current_title, location, source, created_at, updated_at)
        VALUES (gen_random_uuid(), ${params.tenantId}::uuid, ${fullName}, ${email}, ${phone}, ${currentTitle}, ${location}, 'RESUME_UPLOAD', now(), now())
        RETURNING id, full_name as "fullName"
      `;
      candidate = rows[0];
      created = true;
    }

    await this.prisma.resume.update({
      where: { id: params.resumeId },
      data: { candidateId: candidate.id },
    });

    if (created) {
      await this.audit.record({
        tenantId: params.tenantId,
        actorId: params.actorId,
        eventType: "candidate.created",
        entityType: "candidate",
        entityId: candidate.id,
        payload: { source: "resume_upload" },
      });
    }

    if (!params.jobRoleId) {
      return { candidateId: candidate.id, applicationId: null };
    }

    // Same atomic-upsert reasoning as the candidate insert above — attach
    // to an existing pipeline entry rather than erroring if this candidate
    // is already applied to this role.
    const appRows = await this.prisma.$queryRaw<ApplicationRow[]>`
      INSERT INTO applications (id, tenant_id, candidate_id, job_role_id, resume_id, stage, status, stage_entered_at, created_by, created_at, updated_at)
      VALUES (gen_random_uuid(), ${params.tenantId}::uuid, ${candidate.id}::uuid, ${params.jobRoleId}::uuid, ${params.resumeId}::uuid, 'APPLIED', 'ACTIVE', now(), ${params.actorId}, now(), now())
      ON CONFLICT (tenant_id, candidate_id, job_role_id)
      DO UPDATE SET resume_id = EXCLUDED.resume_id, updated_at = now()
      RETURNING id, (xmax = 0) as was_inserted
    `;
    const application = appRows[0];
    const applicationCreated = (application as unknown as { was_inserted: boolean }).was_inserted;

    if (applicationCreated) {
      await this.prisma.applicationStageEvent.create({
        data: {
          tenantId: params.tenantId,
          applicationId: application.id,
          toStage: "APPLIED",
          toStatus: "ACTIVE",
          actorId: "ai-service",
        },
      });
      await this.audit.record({
        tenantId: params.tenantId,
        actorId: params.actorId,
        eventType: "application.created",
        entityType: "application",
        entityId: application.id,
        payload: { candidateId: candidate.id, jobRoleId: params.jobRoleId },
      });
    }

    return { candidateId: candidate.id, applicationId: application.id };
  }
}
