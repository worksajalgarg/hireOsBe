import { createHash } from "crypto";
import { ForbiddenException, Injectable, NotFoundException, UnsupportedMediaTypeException } from "@nestjs/common";
import { Prisma } from "@prisma/client";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";
import { ObjectStorageService } from "../common/storage/object-storage.service";
import { AiServiceClient } from "../common/http/ai-service.client";
import { CandidateLinkingService } from "./candidate-linking.service";
import type { ResumeExtractionPayload } from "../common/types";

const RESUMES_BUCKET = process.env.RESUMES_BUCKET || "candidate-resumes";
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const ALLOWED_MIME = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

@Injectable()
export class ResumesService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
    private readonly storage: ObjectStorageService,
    private readonly aiService: AiServiceClient,
    private readonly candidateLinking: CandidateLinkingService,
  ) {}

  async upload(params: {
    tenantId: string;
    actorId: string;
    jobRoleId: string;
    file: { buffer: Buffer; originalname: string; mimetype: string; size: number };
  }) {
    if (params.file.size > MAX_FILE_BYTES) {
      throw new UnsupportedMediaTypeException(`file exceeds ${MAX_FILE_BYTES / (1024 * 1024)}MB limit`);
    }
    // Never trust the declared content-type alone — sniff magic bytes.
    if (!ALLOWED_MIME.has(params.file.mimetype) || !hasValidMagicBytes(params.file.buffer)) {
      throw new UnsupportedMediaTypeException("only .pdf and .docx resumes are supported");
    }

    const checksum = createHash("sha256").update(params.file.buffer).digest("hex");
    const existing = await this.prisma.resume.findFirst({
      where: { tenantId: params.tenantId, checksumSha256: checksum, deletedAt: null },
      include: { activeExtraction: true },
    });
    if (existing) {
      return { ...existing, duplicate: true };
    }

    const { resume, extraction } = await this.prisma.$transaction(async (tx) => {
      const resume = await tx.resume.create({
        data: {
          tenantId: params.tenantId,
          jobRoleId: params.jobRoleId,
          uploadedBy: params.actorId,
          storageKey: "",
          originalFilename: params.file.originalname,
          mimeType: params.file.mimetype,
          sizeBytes: params.file.size,
          checksumSha256: checksum,
          status: "UPLOADED",
        },
      });
      const key = `${params.tenantId}/resumes/${resume.id}/${slugify(params.file.originalname)}`;
      await this.storage.put({
        bucket: RESUMES_BUCKET,
        key,
        body: params.file.buffer,
        contentType: params.file.mimetype,
      });
      await tx.resume.update({ where: { id: resume.id }, data: { storageKey: key } });
      const extraction = await tx.resumeExtraction.create({
        data: { tenantId: params.tenantId, resumeId: resume.id, status: "RUNNING", startedAt: new Date() },
      });
      return { resume, extraction };
    });

    await this.audit.record({
      tenantId: params.tenantId,
      actorId: params.actorId,
      eventType: "resume.uploaded",
      entityType: "resume",
      entityId: resume.id,
      payload: { jobRoleId: params.jobRoleId, filename: params.file.originalname },
    });

    await this.runExtraction({
      tenantId: params.tenantId,
      actorId: params.actorId,
      resumeId: resume.id,
      extractionId: extraction.id,
      jobRoleId: params.jobRoleId,
      file: params.file,
    });

    return this.findOne(params.tenantId, resume.id);
  }

  async reparse(tenantId: string, actorId: string, id: string, jobRoleId?: string) {
    const resume = await this.findOne(tenantId, id);
    const buffer = await this.storage.get({ bucket: RESUMES_BUCKET, key: resume.storageKey });
    const priorAttempts = await this.prisma.resumeExtraction.count({ where: { resumeId: id } });
    const extraction = await this.prisma.resumeExtraction.create({
      data: { tenantId, resumeId: id, attempt: priorAttempts + 1, status: "RUNNING", startedAt: new Date() },
    });
    await this.runExtraction({
      tenantId,
      actorId,
      resumeId: id,
      extractionId: extraction.id,
      // The controller never passes an explicit jobRoleId — fall back to
      // the role this resume was actually uploaded against (already on the
      // row) so a reparse still re-links the Application, not just the
      // extraction. Without this, every reparse silently dropped the
      // resume out of its pipeline (candidate-linking.service.ts returns
      // applicationId: null whenever jobRoleId is undefined).
      jobRoleId: jobRoleId ?? resume.jobRoleId ?? undefined,
      file: { buffer, originalname: resume.originalFilename, mimetype: resume.mimeType },
    });
    return this.findOne(tenantId, id);
  }

  private async runExtraction(params: {
    tenantId: string;
    actorId: string;
    resumeId: string;
    extractionId: string;
    jobRoleId?: string;
    file: { buffer: Buffer; originalname: string; mimetype: string };
  }) {
    await this.prisma.resume.update({ where: { id: params.resumeId }, data: { status: "PARSING" } });

    try {
      const result = await this.aiService.parseResume({
        buffer: params.file.buffer,
        filename: params.file.originalname,
        mimetype: params.file.mimetype,
      });

      await this.prisma.$transaction([
        this.prisma.resumeExtraction.update({
          where: { id: params.extractionId },
          data: {
            status: "SUCCEEDED",
            extractionJson: result.extraction as unknown as Prisma.InputJsonValue,
            modelVersion: result.modelVersion,
            completedAt: new Date(),
          },
        }),
        this.prisma.resume.update({
          where: { id: params.resumeId },
          data: {
            status: "PARSED",
            activeExtractionId: params.extractionId,
            extractedTextLength: result.extractedTextLength,
          },
        }),
      ]);

      await this.audit.record({
        tenantId: params.tenantId,
        actorId: params.actorId,
        eventType: "resume.parse_completed",
        entityType: "resume",
        entityId: params.resumeId,
        payload: {},
      });

      await this.candidateLinking.linkFromExtraction({
        tenantId: params.tenantId,
        actorId: params.actorId,
        resumeId: params.resumeId,
        jobRoleId: params.jobRoleId,
        extraction: result.extraction as ResumeExtractionPayload,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await this.prisma.$transaction([
        this.prisma.resumeExtraction.update({
          where: { id: params.extractionId },
          data: { status: "FAILED", errorMessage: message, completedAt: new Date() },
        }),
        this.prisma.resume.update({ where: { id: params.resumeId }, data: { status: "PARSE_FAILED" } }),
      ]);
      await this.audit.record({
        tenantId: params.tenantId,
        actorId: params.actorId,
        eventType: "resume.parse_failed",
        entityType: "resume",
        entityId: params.resumeId,
        payload: { error: message },
      });
      // Swallow — the resume row (with a FAILED extraction) is kept either
      // way, and the caller returns it as-is; the frontend shows the error
      // with a retry action rather than failing the whole upload request.
    }
  }

  async listForJobRole(tenantId: string, jobRoleId: string) {
    return this.prisma.resume.findMany({
      where: { tenantId, jobRoleId, deletedAt: null },
      include: { activeExtraction: true },
      orderBy: { createdAt: "desc" },
    });
  }

  async findOne(tenantId: string, id: string) {
    const resume = await this.prisma.resume.findUnique({ where: { id }, include: { activeExtraction: true } });
    if (!resume || resume.deletedAt) throw new NotFoundException("Resume not found");
    if (resume.tenantId !== tenantId) throw new ForbiddenException("Resume belongs to a different tenant");
    return resume;
  }

  async getDownloadUrl(tenantId: string, id: string) {
    const resume = await this.findOne(tenantId, id);
    const url = await this.storage.getSignedDownloadUrl({
      bucket: RESUMES_BUCKET,
      key: resume.storageKey,
      expiresInSeconds: 300,
    });
    return { url };
  }

  async delete(tenantId: string, actorId: string, id: string) {
    const resume = await this.findOne(tenantId, id);
    await this.prisma.resume.update({ where: { id: resume.id }, data: { deletedAt: new Date() } });
    await this.storage.delete({ bucket: RESUMES_BUCKET, key: resume.storageKey });
    await this.audit.record({
      tenantId,
      actorId,
      eventType: "resume.deleted",
      entityType: "resume",
      entityId: id,
      payload: {},
    });
    return { deleted: true };
  }
}

function slugify(filename: string): string {
  return filename.replace(/[^a-zA-Z0-9._-]/g, "_");
}

function hasValidMagicBytes(buffer: Buffer): boolean {
  if (buffer.length < 4) return false;
  const isPdf = buffer.subarray(0, 4).toString("ascii") === "%PDF";
  const isZip = buffer[0] === 0x50 && buffer[1] === 0x4b && buffer[2] === 0x03 && buffer[3] === 0x04;
  return isPdf || isZip; // .docx is a zip container (PK\x03\x04)
}
