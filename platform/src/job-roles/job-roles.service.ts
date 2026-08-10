import { ForbiddenException, Injectable, NotFoundException } from "@nestjs/common";
import { Prisma } from "@prisma/client";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";
import { ObjectStorageService } from "../common/storage/object-storage.service";
import {
  AiServiceClient,
  UnparsableDocumentError,
  UnsupportedFileTypeError,
} from "../common/http/ai-service.client";
import { JobRoleStatusInput } from "./dto";

const JD_BUCKET = process.env.JD_BUCKET || "job-descriptions";

@Injectable()
export class JobRolesService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
    private readonly storage: ObjectStorageService,
    private readonly aiService: AiServiceClient,
  ) {}

  async createFromText(params: {
    tenantId: string;
    actorId: string;
    title: string;
    jdText: string;
    department?: string;
    location?: string;
    employmentType?: string;
    seniority?: string;
  }) {
    const { jobRole, extraction } = await this.prisma.$transaction(async (tx) => {
      const jobRole = await tx.jobRole.create({
        data: {
          tenantId: params.tenantId,
          title: params.title,
          department: params.department,
          location: params.location,
          employmentType: params.employmentType,
          seniority: params.seniority,
          jdSourceType: "PASTE",
          jdText: params.jdText,
          createdBy: params.actorId,
        },
      });
      const extraction = await tx.jobRoleExtraction.create({
        data: { tenantId: params.tenantId, jobRoleId: jobRole.id, status: "RUNNING", startedAt: new Date() },
      });
      return { jobRole, extraction };
    });

    return this.runExtraction({
      tenantId: params.tenantId,
      actorId: params.actorId,
      jobRoleId: jobRole.id,
      extractionId: extraction.id,
      parse: () => this.aiService.parseJobDescriptionText(params.jdText),
    });
  }

  async createFromFile(params: {
    tenantId: string;
    actorId: string;
    title: string;
    department?: string;
    location?: string;
    employmentType?: string;
    seniority?: string;
    file: { buffer: Buffer; originalname: string; mimetype: string; size: number };
  }) {
    const { jobRole, extraction } = await this.prisma.$transaction(async (tx) => {
      const jobRole = await tx.jobRole.create({
        data: {
          tenantId: params.tenantId,
          title: params.title,
          department: params.department,
          location: params.location,
          employmentType: params.employmentType,
          seniority: params.seniority,
          jdSourceType: "UPLOAD",
          jdFileName: params.file.originalname,
          jdMimeType: params.file.mimetype,
          jdSizeBytes: params.file.size,
          createdBy: params.actorId,
        },
      });
      const key = `${params.tenantId}/job-roles/${jobRole.id}/${slugify(params.file.originalname)}`;
      await this.storage.put({
        bucket: JD_BUCKET,
        key,
        body: params.file.buffer,
        contentType: params.file.mimetype,
      });
      await tx.jobRole.update({ where: { id: jobRole.id }, data: { jdFileKey: key } });
      const extraction = await tx.jobRoleExtraction.create({
        data: { tenantId: params.tenantId, jobRoleId: jobRole.id, status: "RUNNING", startedAt: new Date() },
      });
      return { jobRole, extraction };
    });

    return this.runExtraction({
      tenantId: params.tenantId,
      actorId: params.actorId,
      jobRoleId: jobRole.id,
      extractionId: extraction.id,
      parse: () =>
        this.aiService.parseJobDescriptionFile({
          buffer: params.file.buffer,
          filename: params.file.originalname,
          mimetype: params.file.mimetype,
        }),
      persistJdText: true,
    });
  }

  private async runExtraction(params: {
    tenantId: string;
    actorId: string;
    jobRoleId: string;
    extractionId: string;
    parse: () => Promise<{
      extraction: unknown;
      extractedText?: string;
      modelVersion: string;
    }>;
    persistJdText?: boolean;
  }) {
    try {
      const result = await params.parse();
      await this.prisma.$transaction([
        this.prisma.jobRoleExtraction.update({
          where: { id: params.extractionId },
          data: {
            status: "SUCCEEDED",
            extractionJson: result.extraction as Prisma.InputJsonValue,
            modelVersion: result.modelVersion,
            completedAt: new Date(),
          },
        }),
        this.prisma.jobRole.update({
          where: { id: params.jobRoleId },
          data: {
            activeExtractionId: params.extractionId,
            ...(params.persistJdText && result.extractedText ? { jdText: result.extractedText } : {}),
          },
        }),
      ]);
      await this.audit.record({
        tenantId: params.tenantId,
        actorId: params.actorId,
        eventType: "job_role.jd_parsed",
        entityType: "job_role",
        entityId: params.jobRoleId,
        payload: {},
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await this.prisma.jobRoleExtraction.update({
        where: { id: params.extractionId },
        data: { status: "FAILED", errorMessage: message, completedAt: new Date() },
      });
      await this.audit.record({
        tenantId: params.tenantId,
        actorId: params.actorId,
        eventType: "job_role.jd_parse_failed",
        entityType: "job_role",
        entityId: params.jobRoleId,
        payload: { error: message },
      });
      if (err instanceof UnsupportedFileTypeError || err instanceof UnparsableDocumentError) {
        // Surface the original 4xx-shaped error to the controller/caller
        // rather than a generic failure — the JD upload itself succeeded,
        // only extraction failed, so the JobRole/JD file are kept either way.
        throw err;
      }
      // Any other failure (ai-service unreachable, timeout) still returns
      // the created JobRole with a FAILED extraction rather than rolling
      // back the whole creation — the recruiter can re-parse from the UI.
    }

    await this.audit.record({
      tenantId: params.tenantId,
      actorId: params.actorId,
      eventType: "job_role.created",
      entityType: "job_role",
      entityId: params.jobRoleId,
      payload: {},
    });

    return this.findOne(params.tenantId, params.jobRoleId);
  }

  async findAll(tenantId: string, filters: { status?: string; q?: string }) {
    return this.prisma.jobRole.findMany({
      where: {
        tenantId,
        deletedAt: null,
        ...(filters.status ? { status: filters.status as never } : {}),
        ...(filters.q ? { title: { contains: filters.q, mode: "insensitive" } } : {}),
      },
      include: { activeExtraction: true },
      orderBy: { createdAt: "desc" },
    });
  }

  async findOne(tenantId: string, id: string) {
    const jobRole = await this.prisma.jobRole.findUnique({
      where: { id },
      include: { activeExtraction: true },
    });
    if (!jobRole || jobRole.deletedAt) throw new NotFoundException("Job role not found");
    if (jobRole.tenantId !== tenantId) throw new ForbiddenException("Job role belongs to a different tenant");
    return jobRole;
  }

  async update(tenantId: string, actorId: string, id: string, patch: Record<string, unknown>) {
    const existing = await this.findOne(tenantId, id);
    const updated = await this.prisma.jobRole.update({ where: { id: existing.id }, data: patch });
    await this.audit.record({
      tenantId,
      actorId,
      eventType: "job_role.updated",
      entityType: "job_role",
      entityId: id,
      payload: { fields: Object.keys(patch) },
    });
    return updated;
  }

  async setStatus(tenantId: string, actorId: string, id: string, status: JobRoleStatusInput) {
    const existing = await this.findOne(tenantId, id);
    const updated = await this.prisma.jobRole.update({
      where: { id: existing.id },
      data: { status, ...(status === "CLOSED" ? { closedAt: new Date() } : {}) },
    });
    await this.audit.record({
      tenantId,
      actorId,
      eventType: "job_role.status_changed",
      entityType: "job_role",
      entityId: id,
      payload: { from: existing.status, to: status },
    });
    return updated;
  }

  async reparse(tenantId: string, actorId: string, id: string) {
    const jobRole = await this.findOne(tenantId, id);
    if (!jobRole.jdText) {
      throw new NotFoundException("Job role has no JD text to re-parse");
    }
    const priorAttempts = await this.prisma.jobRoleExtraction.count({ where: { jobRoleId: jobRole.id } });
    const extraction = await this.prisma.jobRoleExtraction.create({
      data: {
        tenantId,
        jobRoleId: jobRole.id,
        attempt: priorAttempts + 1,
        status: "RUNNING",
        startedAt: new Date(),
      },
    });
    return this.runExtraction({
      tenantId,
      actorId,
      jobRoleId: jobRole.id,
      extractionId: extraction.id,
      parse: () => this.aiService.parseJobDescriptionText(jobRole.jdText as string),
    });
  }

  async getJdDownloadUrl(tenantId: string, id: string) {
    const jobRole = await this.findOne(tenantId, id);
    if (!jobRole.jdFileKey) throw new NotFoundException("Job role has no uploaded JD file");
    const url = await this.storage.getSignedDownloadUrl({
      bucket: JD_BUCKET,
      key: jobRole.jdFileKey,
      expiresInSeconds: 300,
    });
    return { url };
  }
}

function slugify(filename: string): string {
  return filename.replace(/[^a-zA-Z0-9._-]/g, "_");
}
