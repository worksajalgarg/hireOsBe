import { ForbiddenException, Injectable, NotFoundException } from "@nestjs/common";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";

@Injectable()
export class CandidatesService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
  ) {}

  async findAll(tenantId: string, q?: string) {
    return this.prisma.candidate.findMany({
      where: {
        tenantId,
        deletedAt: null,
        ...(q ? { fullName: { contains: q, mode: "insensitive" } } : {}),
      },
      orderBy: { createdAt: "desc" },
    });
  }

  async findOne(tenantId: string, id: string) {
    const candidate = await this.prisma.candidate.findUnique({
      where: { id },
      include: {
        resumes: {
          where: { deletedAt: null },
          include: { activeExtraction: true },
          orderBy: { createdAt: "desc" },
        },
        applications: {
          include: { jobRole: { select: { id: true, title: true, status: true } } },
          orderBy: { createdAt: "desc" },
        },
      },
    });
    if (!candidate || candidate.deletedAt) throw new NotFoundException("Candidate not found");
    if (candidate.tenantId !== tenantId) throw new ForbiddenException("Candidate belongs to a different tenant");
    return candidate;
  }

  async update(tenantId: string, actorId: string, id: string, patch: Record<string, unknown>) {
    const existing = await this.findOne(tenantId, id);
    const updated = await this.prisma.candidate.update({ where: { id: existing.id }, data: patch });
    await this.audit.record({
      tenantId,
      actorId,
      eventType: "candidate.updated",
      entityType: "candidate",
      entityId: id,
      payload: { fields: Object.keys(patch) },
    });
    return updated;
  }
}
