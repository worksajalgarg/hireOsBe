import {
  BadRequestException,
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
    const base = filename.split("/").pop() ?? filename;
    const i = base.lastIndexOf(".");
    return i >= 0 ? base.slice(i).toLowerCase() : "";
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
      // extension already validated
    }
  }

  async upload(params: {
    tenantId: string;
    userId: string;
    filename: string;
    contentType: string;
    buffer: Buffer;
  }) {
    this.validateUpload(params.filename, params.contentType, params.buffer.length);
    await this.prisma.setTenantContext(params.tenantId);

    const id = randomUUID();
    const storageKey = this.storage.buildResumeKey(
      params.tenantId,
      id,
      params.filename,
    );

    await this.storage.putObject({
      key: storageKey,
      body: params.buffer,
      contentType: params.contentType || "application/octet-stream",
    });

    const resume = await this.prisma.resume.create({
      data: {
        id,
        tenantId: params.tenantId,
        createdByUserId: params.userId,
        originalFilename: params.filename,
        contentType: params.contentType || "application/octet-stream",
        sizeBytes: params.buffer.length,
        storageKey,
        status: ResumeStatus.UPLOADED,
      },
    });

    return this.toListItem(resume);
  }

  async list(tenantId: string) {
    await this.prisma.setTenantContext(tenantId);
    const rows = await this.prisma.resume.findMany({
      where: { tenantId },
      orderBy: { createdAt: "desc" },
    });
    return rows.map((r) => this.toListItem(r));
  }

  async get(tenantId: string, id: string) {
    await this.prisma.setTenantContext(tenantId);
    const resume = await this.prisma.resume.findFirst({
      where: { id, tenantId },
    });
    if (!resume) throw new NotFoundException(`Resume ${id} not found`);
    return this.toDetail(resume);
  }

  async updateWorkingJson(
    tenantId: string,
    id: string,
    workingJson: Record<string, unknown>,
  ) {
    await this.prisma.setTenantContext(tenantId);
    const existing = await this.prisma.resume.findFirst({
      where: { id, tenantId },
    });
    if (!existing) throw new NotFoundException(`Resume ${id} not found`);

    const resume = await this.prisma.resume.update({
      where: { id },
      data: {
        workingJson: workingJson as Prisma.InputJsonValue,
        status: ResumeStatus.EDITED,
        errorMessage: null,
      },
    });
    return this.toDetail(resume);
  }

  async delete(tenantId: string, id: string) {
    await this.prisma.setTenantContext(tenantId);
    const existing = await this.prisma.resume.findFirst({
      where: { id, tenantId },
    });
    if (!existing) throw new NotFoundException(`Resume ${id} not found`);

    try {
      await this.storage.deleteObject(existing.storageKey);
    } catch {
      // continue DB delete even if object already gone
    }
    await this.prisma.resume.delete({ where: { id } });
    return { ok: true };
  }

  async markExtracting(tenantId: string, id: string) {
    await this.prisma.setTenantContext(tenantId);
    const existing = await this.prisma.resume.findFirst({
      where: { id, tenantId },
    });
    if (!existing) throw new NotFoundException(`Resume ${id} not found`);
    return this.prisma.resume.update({
      where: { id },
      data: { status: ResumeStatus.EXTRACTING, errorMessage: null },
    });
  }

  async getFileBuffer(tenantId: string, id: string) {
    const resume = await this.markExtracting(tenantId, id);
    const buffer = await this.storage.getObjectBuffer(resume.storageKey);
    return { resume, buffer };
  }

  async persistExtractionSuccess(
    tenantId: string,
    id: string,
    payload: {
      resumeJson: Record<string, unknown>;
      parseSource?: string | null;
    },
  ) {
    await this.prisma.setTenantContext(tenantId);
    return this.prisma.resume.update({
      where: { id },
      data: {
        extractedJson: payload.resumeJson as Prisma.InputJsonValue,
        workingJson: payload.resumeJson as Prisma.InputJsonValue,
        parseSource: payload.parseSource ?? null,
        status: ResumeStatus.EXTRACTED,
        errorMessage: null,
      },
    });
  }

  async persistExtractionFailure(tenantId: string, id: string, message: string) {
    await this.prisma.setTenantContext(tenantId);
    return this.prisma.resume.update({
      where: { id },
      data: {
        status: ResumeStatus.FAILED,
        errorMessage: message.slice(0, 2000),
      },
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
      storageKey: resume.storageKey,
      extractedJson: resume.extractedJson,
      workingJson: resume.workingJson,
      parseSource: resume.parseSource,
      errorMessage: resume.errorMessage,
    };
  }
}
