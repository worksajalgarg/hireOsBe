import { Injectable, NotFoundException } from "@nestjs/common";
import { Prisma } from "@prisma/client";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";
import { RbacSeedService } from "../common/rbac-seed.service";
import { SYSTEM_ROLE_NAMES } from "../common/permissions";
import { UpdateWorkspaceSettingsDto } from "../auth/dto";

@Injectable()
export class TenantService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly auditService: AuditService,
    private readonly rbacSeed: RbacSeedService,
  ) {}

  async create(params: { name: string; domain: string; actorId: string }) {
    const tenant = await this.prisma.tenant.create({
      data: {
        name: params.name,
        domain: params.domain,
        policies: {
          create: {},
        },
      },
    });

    await this.rbacSeed.seedSystemRolesForTenant(tenant.id);

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

  async findById(tenantId: string) {
    const tenant = await this.prisma.tenant.findUnique({ where: { id: tenantId } });
    if (!tenant) {
      throw new NotFoundException(`Tenant ${tenantId} not found`);
    }
    return tenant;
  }

  async getSettings(tenantId: string) {
    const tenant = await this.findById(tenantId);
    let policy = await this.prisma.tenantPolicy.findUnique({ where: { tenantId } });
    if (!policy) {
      policy = await this.prisma.tenantPolicy.create({ data: { tenantId } });
    }
    return {
      tenant: {
        id: tenant.id,
        name: tenant.name,
        domain: tenant.domain,
        logoUrl: tenant.logoUrl,
        settingsJson: tenant.settingsJson as Record<string, unknown>,
        createdAt: tenant.createdAt.toISOString(),
        updatedAt: tenant.updatedAt.toISOString(),
      },
      policy: {
        id: policy.id,
        tenantId: policy.tenantId,
        retentionDays: policy.retentionDays,
        audioStorageEnabled: policy.audioStorageEnabled,
        humanOverrideRequired: policy.humanOverrideRequired,
        updatedAt: policy.updatedAt.toISOString(),
      },
    };
  }

  async updateSettings(tenantId: string, actorId: string, dto: UpdateWorkspaceSettingsDto) {
    await this.prisma.setTenantContext(tenantId);

    const tenant = await this.prisma.tenant.update({
      where: { id: tenantId },
      data: {
        name: dto.name,
        domain: dto.domain,
        logoUrl: dto.logoUrl,
        settingsJson:
          dto.settingsJson === undefined
            ? undefined
            : (dto.settingsJson as Prisma.InputJsonValue),
      },
    });

    const policy = await this.prisma.tenantPolicy.upsert({
      where: { tenantId },
      create: {
        tenantId,
        retentionDays: dto.retentionDays ?? 90,
        audioStorageEnabled: dto.audioStorageEnabled ?? false,
        humanOverrideRequired: dto.humanOverrideRequired ?? true,
        updatedBy: actorId,
      },
      update: {
        retentionDays: dto.retentionDays,
        audioStorageEnabled: dto.audioStorageEnabled,
        humanOverrideRequired: dto.humanOverrideRequired,
        updatedBy: actorId,
      },
    });

    await this.auditService.record({
      tenantId,
      actorId,
      eventType: "workspace.settings_updated",
      entityType: "tenant",
      entityId: tenantId,
      payload: { ...dto },
    });

    return {
      tenant: {
        id: tenant.id,
        name: tenant.name,
        domain: tenant.domain,
        logoUrl: tenant.logoUrl,
        settingsJson: tenant.settingsJson as Record<string, unknown>,
        createdAt: tenant.createdAt.toISOString(),
        updatedAt: tenant.updatedAt.toISOString(),
      },
      policy: {
        id: policy.id,
        tenantId: policy.tenantId,
        retentionDays: policy.retentionDays,
        audioStorageEnabled: policy.audioStorageEnabled,
        humanOverrideRequired: policy.humanOverrideRequired,
        updatedAt: policy.updatedAt.toISOString(),
      },
    };
  }

  async ensureAdminRoleId(tenantId: string) {
    return (
      (await this.rbacSeed.findSystemRoleId(tenantId, SYSTEM_ROLE_NAMES.Admin)) ??
      (() => {
        throw new NotFoundException("Admin role missing for tenant");
      })()
    );
  }
}
