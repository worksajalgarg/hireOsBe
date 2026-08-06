import {
  BadRequestException,
  ConflictException,
  Injectable,
  NotFoundException,
} from "@nestjs/common";
import { Prisma, ResumeStatus } from "@prisma/client";
import { randomUUID } from "crypto";
import { PrismaService } from "../common/prisma.service";
import { ObjectStorageService } from "../common/storage/object-storage.service";

const ALLOWED_EXT = new Set([
  ".pdf",
  ".docx",
  ".doc",
  ".odt",
  ".html",
  ".htm",
  ".md",
  ".markdown",
  ".adoc",
  ".asciidoc",
  ".png",
  ".jpg",
  ".jpeg",
  ".webp",
  ".tif",
  ".tiff",
  ".bmp",
]);
const ALLOWED_MIME = new Set([
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.oasis.opendocument.text",
  "text/html",
  "application/xhtml+xml",
  "text/markdown",
  "text/x-markdown",
  "text/plain",
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/tiff",
  "image/bmp",
  "application/octet-stream",
]);

@Injectable()
export class ResumesService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly storage: ObjectStorageService,
  ) {}

  private maxUploadBytes(): number {
    const mb = Number(process.env.RESUME_MAX_UPLOAD_MB ?? "10");
    return (Number.isFinite(mb) && mb > 0 ? mb : 10) * 1024 * 1024;
  }

  private extension(filename: string): string {
    const base = filename.replace(/\\/g, "/").split("/").pop() ?? filename;
    const i = base.lastIndexOf(".");
    return i >= 0 ? base.slice(i).toLowerCase() : "";
  }

  private sanitizeFilename(filename: string): string {
    const base = filename.replace(/\\/g, "/").split("/").pop()?.trim() ?? "";
    const safe = [...base]
      .filter((character) => {
        const code = character.charCodeAt(0);
        return code >= 32 && code !== 127;
      })
      .join("")
      .slice(0, 240);
    if (!safe || safe === "." || safe === "..") {
      throw new BadRequestException("Filename is invalid");
    }
    return safe;
  }

  private validateUpload(filename: string, contentType: string, size: number) {
    const ext = this.extension(filename);
    if (!ALLOWED_EXT.has(ext)) {
      throw new BadRequestException(
        `Unsupported file type '${ext}'. Allowed: PDF, DOC, DOCX, ODT, HTML, Markdown, or image`,
      );
    }
    if (size <= 0) {
      throw new BadRequestException("File is empty");
    }
    if (size > this.maxUploadBytes()) {
      throw new BadRequestException(
        `File exceeds maximum size of ${process.env.RESUME_MAX_UPLOAD_MB ?? 10}MB`,
      );
    }
    const mime = contentType.split(";")[0].trim().toLowerCase();
    if (mime && !ALLOWED_MIME.has(mime)) {
      throw new BadRequestException(`Unsupported content type '${mime}'`);
    }
  }

  private validateWorkingJsonShape(workingJson: Record<string, unknown>) {
    if (workingJson.schema_version !== "2.0") {
      throw new BadRequestException("workingJson.schema_version must be '2.0'");
    }
    if (!workingJson.contact || typeof workingJson.contact !== "object") {
      throw new BadRequestException("workingJson.contact must be an object");
    }
    for (const field of [
      "experience",
      "education",
      "skills",
      "projects",
      "certifications",
      "languages",
    ]) {
      if (!Array.isArray(workingJson[field])) {
        throw new BadRequestException(`workingJson.${field} must be an array`);
      }
    }
  }

  async upload(params: {
    tenantId: string;
    userId: string;
    filename: string;
    contentType: string;
    buffer: Buffer;
  }) {
    const filename = this.sanitizeFilename(params.filename);
    this.validateUpload(filename, params.contentType, params.buffer.length);
    const id = randomUUID();
    const storageKey = this.storage.buildResumeKey(
      params.tenantId,
      id,
      filename,
    );

    await this.storage.putObject({
      key: storageKey,
      body: params.buffer,
      contentType: params.contentType || "application/octet-stream",
    });

    let resume;
    try {
      resume = await this.prisma.withTenant(params.tenantId, (tx) =>
        tx.resume.create({
          data: {
            id,
            tenantId: params.tenantId,
            createdByUserId: params.userId,
            originalFilename: filename,
            contentType: params.contentType || "application/octet-stream",
            sizeBytes: params.buffer.length,
            storageKey,
            status: ResumeStatus.UPLOADED,
          },
        }),
      );
    } catch (error) {
      await this.storage.deleteObject(storageKey).catch(() => undefined);
      throw error;
    }

    return this.toListItem(resume);
  }

  async list(tenantId: string) {
    const rows = await this.prisma.withTenant(tenantId, (tx) =>
      tx.resume.findMany({
        where: { tenantId },
        orderBy: { createdAt: "desc" },
      }),
    );
    return rows.map((r) => this.toListItem(r));
  }

  async get(tenantId: string, id: string) {
    const resume = await this.prisma.withTenant(tenantId, (tx) =>
      tx.resume.findFirst({ where: { id, tenantId } }),
    );
    if (!resume) throw new NotFoundException(`Resume ${id} not found`);
    return this.toDetail(resume);
  }

  async updateWorkingJson(
    tenantId: string,
    id: string,
    workingJson: Record<string, unknown>,
  ) {
    this.validateWorkingJsonShape(workingJson);
    const resume = await this.prisma.withTenant(tenantId, async (tx) => {
      const existing = await tx.resume.findFirst({ where: { id, tenantId } });
      if (!existing) throw new NotFoundException(`Resume ${id} not found`);
      if (existing.status === ResumeStatus.EXTRACTING) {
        throw new ConflictException("Cannot edit JSON while extraction is running");
      }
      return tx.resume.update({
        where: { id },
        data: {
          workingJson: workingJson as Prisma.InputJsonValue,
          status: ResumeStatus.EDITED,
          errorMessage: null,
        },
      });
    });
    return this.toDetail(resume);
  }

  async delete(tenantId: string, id: string) {
    const existing = await this.prisma.withTenant(tenantId, async (tx) => {
      const row = await tx.resume.findFirst({ where: { id, tenantId } });
      if (!row) throw new NotFoundException(`Resume ${id} not found`);
      if (row.status === ResumeStatus.EXTRACTING) {
        throw new ConflictException("Cannot delete a resume while extraction is running");
      }
      await tx.resume.delete({ where: { id } });
      return row;
    });
    await this.storage.deleteObject(existing.storageKey).catch(() => undefined);
    return { ok: true };
  }

  async markExtracting(tenantId: string, id: string) {
    return this.prisma.withTenant(tenantId, async (tx) => {
      const existing = await tx.resume.findFirst({ where: { id, tenantId } });
      if (!existing) throw new NotFoundException(`Resume ${id} not found`);
      if (existing.status === ResumeStatus.EXTRACTING) {
        throw new ConflictException("Resume extraction is already running");
      }
      return tx.resume.update({
        where: { id },
        data: { status: ResumeStatus.EXTRACTING, errorMessage: null },
      });
    });
  }

  async getFileBuffer(tenantId: string, id: string) {
    const resume = await this.markExtracting(tenantId, id);
    try {
      const buffer = await this.storage.getObjectBuffer(resume.storageKey);
      return { resume, buffer };
    } catch (error) {
      await this.persistExtractionFailure(tenantId, id, (error as Error).message);
      throw error;
    }
  }

  async persistExtractionSuccess(
    tenantId: string,
    id: string,
    payload: {
      resumeJson: Record<string, unknown>;
      parseSource?: string | null;
    },
  ) {
    return this.prisma.withTenant(tenantId, async (tx) => {
      const existing = await tx.resume.findFirst({ where: { id, tenantId } });
      if (!existing) throw new NotFoundException(`Resume ${id} not found`);
      return tx.resume.update({
        where: { id },
        data: {
          extractedJson: payload.resumeJson as Prisma.InputJsonValue,
          // Preserve recruiter edits when a resume is re-extracted.
          workingJson:
            existing.workingJson ?? (payload.resumeJson as Prisma.InputJsonValue),
          parseSource: payload.parseSource ?? null,
          status: existing.workingJson ? ResumeStatus.EDITED : ResumeStatus.EXTRACTED,
          errorMessage: null,
        },
      });
    });
  }

  async persistExtractionFailure(tenantId: string, id: string, message: string) {
    return this.prisma.withTenant(tenantId, async (tx) => {
      const existing = await tx.resume.findFirst({ where: { id, tenantId } });
      if (!existing) throw new NotFoundException(`Resume ${id} not found`);
      return tx.resume.update({
        where: { id },
        data: {
          status: existing.workingJson ? ResumeStatus.EDITED : ResumeStatus.FAILED,
          errorMessage: message.slice(0, 2000),
        },
      });
    });
  }

  private contactName(json: unknown): string | null {
    if (!json || typeof json !== "object") return null;
    const contact = (json as { contact?: { full_name?: string | null } }).contact;
    return contact?.full_name ?? null;
  }

  private toListItem(resume: {
    id: string;
    originalFilename: string;
    contentType: string;
    sizeBytes: number;
    status: ResumeStatus;
    workingJson: unknown;
    extractedJson: unknown;
    createdAt: Date;
    updatedAt: Date;
  }) {
    return {
      id: resume.id,
      originalFilename: resume.originalFilename,
      contentType: resume.contentType,
      sizeBytes: resume.sizeBytes,
      status: resume.status,
      contactName:
        this.contactName(resume.workingJson) ??
        this.contactName(resume.extractedJson),
      createdAt: resume.createdAt.toISOString(),
      updatedAt: resume.updatedAt.toISOString(),
    };
  }

  private toDetail(resume: {
    id: string;
    tenantId: string;
    createdByUserId: string;
    originalFilename: string;
    contentType: string;
    sizeBytes: number;
    storageKey: string;
    status: ResumeStatus;
    extractedJson: unknown;
    workingJson: unknown;
    parseSource: string | null;
    errorMessage: string | null;
    createdAt: Date;
    updatedAt: Date;
  }) {
    return {
      ...this.toListItem(resume),
      tenantId: resume.tenantId,
      createdByUserId: resume.createdByUserId,
      extractedJson: resume.extractedJson,
      workingJson: resume.workingJson,
      parseSource: resume.parseSource,
      errorMessage: resume.errorMessage,
    };
  }
}
