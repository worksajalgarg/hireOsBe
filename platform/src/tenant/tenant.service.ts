import { Injectable, NotFoundException } from "@nestjs/common";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";

@Injectable()
export class TenantService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly auditService: AuditService,
  ) {}

  async create(params: { name: string; domain: string; actorId: string }) {
    const tenant = await this.prisma.tenant.create({
      data: { name: params.name, domain: params.domain },
    });

    await this.auditService.record({
      tenantId: tenant.id,
      actorId: params.actorId,
      eventType: "tenant.created",
      entityType: "tenant",
      entityId: tenant.id,
      payload: { name: tenant.name, domain: tenant.domain },
    });

    return tenant;
  }

  /** Always scoped by id — there is no "list all tenants" path for tenant-facing callers. */
  async findById(tenantId: string) {
    const tenant = await this.prisma.tenant.findUnique({ where: { id: tenantId } });
    if (!tenant) {
      throw new NotFoundException(`Tenant ${tenantId} not found`);
    }
    return tenant;
  }
}
