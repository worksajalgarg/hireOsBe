import {
  BadRequestException,
  ConflictException,
  ForbiddenException,
  Injectable,
  NotFoundException,
} from "@nestjs/common";
import { Prisma } from "@prisma/client";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";
import { ApplicationStageInput, ApplicationStatusInput, APPLICATION_STAGES } from "./dto";

@Injectable()
export class ApplicationsService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
  ) {}

  /** Grouped by stage, in funnel order — the shape the pipeline table reads
   * directly, no client-side grouping needed. */
  async listPipeline(tenantId: string, jobRoleId: string) {
    const applications = await this.prisma.application.findMany({
      where: { tenantId, jobRoleId },
      include: { candidate: true },
      orderBy: { stageEnteredAt: "desc" },
    });
    const grouped: Record<string, typeof applications> = {};
    for (const stage of APPLICATION_STAGES) grouped[stage] = [];
    for (const app of applications) {
      (grouped[app.stage] ??= []).push(app);
    }
    return grouped;
  }

  async create(tenantId: string, actorId: string, params: { candidateId: string; jobRoleId: string }) {
    const [candidate, jobRole] = await Promise.all([
      this.prisma.candidate.findUnique({ where: { id: params.candidateId } }),
      this.prisma.jobRole.findUnique({ where: { id: params.jobRoleId } }),
    ]);
    if (!candidate || candidate.tenantId !== tenantId) throw new NotFoundException("Candidate not found");
    if (!jobRole || jobRole.tenantId !== tenantId) throw new NotFoundException("Job role not found");

    let application;
    try {
      application = await this.prisma.application.create({
        data: {
          tenantId,
          candidateId: params.candidateId,
          jobRoleId: params.jobRoleId,
          createdBy: actorId,
        },
      });
    } catch (err) {
      if (err instanceof Prisma.PrismaClientKnownRequestError && err.code === "P2002") {
        throw new ConflictException("This candidate is already in this role's pipeline");
      }
      throw err;
    }

    await this.prisma.applicationStageEvent.create({
      data: {
        tenantId,
        applicationId: application.id,
        toStage: "APPLIED",
        toStatus: "ACTIVE",
        actorId,
      },
    });

    await this.audit.record({
      tenantId,
      actorId,
      eventType: "application.created",
      entityType: "application",
      entityId: application.id,
      payload: { candidateId: params.candidateId, jobRoleId: params.jobRoleId },
    });

    return application;
  }

  /** v1 transition rule: any forward/backward stage move is allowed on an
   * ACTIVE application (recruiters correct mistakes often); moving a
   * non-ACTIVE (already disposed) application requires an explicit reopen
   * (setDisposition back to ACTIVE) first — arbitrary reordering of a
   * rejected candidate is the bug worth blocking, not honest corrections. */
  async moveStage(
    tenantId: string,
    actorId: string,
    id: string,
    params: { toStage: ApplicationStageInput; note?: string },
  ) {
    const application = await this.getTenantApplication(tenantId, id);
    if (application.status !== "ACTIVE") {
      throw new BadRequestException(
        `Cannot move stage on an application with status ${application.status} — reopen it first`,
      );
    }

    const [updated] = await this.prisma.$transaction([
      this.prisma.application.update({
        where: { id: application.id },
        data: { stage: params.toStage, stageEnteredAt: new Date() },
      }),
      this.prisma.applicationStageEvent.create({
        data: {
          tenantId,
          applicationId: application.id,
          fromStage: application.stage,
          toStage: params.toStage,
          fromStatus: application.status,
          toStatus: application.status,
          actorId,
          note: params.note,
        },
      }),
    ]);

    await this.audit.record({
      tenantId,
      actorId,
      eventType: "application.stage_changed",
      entityType: "application",
      entityId: id,
      payload: { from: application.stage, to: params.toStage },
    });

    return updated;
  }

  async setDisposition(
    tenantId: string,
    actorId: string,
    id: string,
    params: { status: ApplicationStatusInput; reason?: string },
  ) {
    const application = await this.getTenantApplication(tenantId, id);

    const [updated] = await this.prisma.$transaction([
      this.prisma.application.update({
        where: { id: application.id },
        data: { status: params.status, dispositionReason: params.reason },
      }),
      this.prisma.applicationStageEvent.create({
        data: {
          tenantId,
          applicationId: application.id,
          fromStage: application.stage,
          toStage: application.stage,
          fromStatus: application.status,
          toStatus: params.status,
          actorId,
          note: params.reason,
        },
      }),
    ]);

    await this.audit.record({
      tenantId,
      actorId,
      eventType: "application.disposition",
      entityType: "application",
      entityId: id,
      payload: { from: application.status, to: params.status, reason: params.reason },
    });

    return updated;
  }

  private async getTenantApplication(tenantId: string, id: string) {
    const application = await this.prisma.application.findUnique({ where: { id } });
    if (!application) throw new NotFoundException("Application not found");
    if (application.tenantId !== tenantId) throw new ForbiddenException("Application belongs to a different tenant");
    return application;
  }
}
