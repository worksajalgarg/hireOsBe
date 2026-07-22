import { Injectable } from "@nestjs/common";
import { Prisma } from "@prisma/client";
import { AuditEventType } from "../common/types";
import { PrismaService } from "../common/prisma.service";

@Injectable()
export class AuditService {
  constructor(private readonly prisma: PrismaService) {}

  async record(params: {
    tenantId: string;
    actorId: string;
    eventType: AuditEventType;
    entityType: string;
    entityId: string;
    payload?: Record<string, unknown>;
  }) {
    return this.prisma.auditEvent.create({
      data: {
        tenantId: params.tenantId,
        actorId: params.actorId,
        eventType: params.eventType,
        entityType: params.entityType,
        entityId: params.entityId,
        payload: (params.payload ?? {}) as Prisma.InputJsonValue,
      },
    });
  }

  /** Scoped strictly to the requesting tenant — never accepts a cross-tenant read. */
  async listForTenant(tenantId: string) {
    return this.prisma.auditEvent.findMany({
      where: { tenantId },
      orderBy: { createdAt: "desc" },
    });
  }
}
