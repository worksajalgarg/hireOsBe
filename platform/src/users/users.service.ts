import { Injectable } from "@nestjs/common";
import { UserRole as SharedUserRole } from "../common/types";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";

const toPrismaRole = (role: SharedUserRole) => role.toUpperCase() as "RECRUITER" | "HIRING_MANAGER" | "ADMIN" | "AUDITOR";

@Injectable()
export class UsersService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly auditService: AuditService,
  ) {}

  /** Every read is scoped by tenantId — there is no cross-tenant user lookup. */
  async invite(params: { tenantId: string; email: string; role: SharedUserRole; actorId: string }) {
    const user = await this.prisma.user.create({
      data: {
        tenantId: params.tenantId,
        email: params.email,
        role: toPrismaRole(params.role),
      },
    });

    await this.auditService.record({
      tenantId: params.tenantId,
      actorId: params.actorId,
      eventType: "user.invited",
      entityType: "user",
      entityId: user.id,
      payload: { email: user.email, role: user.role },
    });

    return user;
  }

  async listForTenant(tenantId: string) {
    return this.prisma.user.findMany({ where: { tenantId } });
  }

  async changeRole(params: { tenantId: string; userId: string; role: SharedUserRole; actorId: string }) {
    const user = await this.prisma.user.update({
      where: { id: params.userId, tenantId: params.tenantId },
      data: { role: toPrismaRole(params.role) },
    });

    await this.auditService.record({
      tenantId: params.tenantId,
      actorId: params.actorId,
      eventType: "user.role_changed",
      entityType: "user",
      entityId: user.id,
      payload: { newRole: user.role },
    });

    return user;
  }
}
