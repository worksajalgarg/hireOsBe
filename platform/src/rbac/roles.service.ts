import { BadRequestException, Injectable } from "@nestjs/common";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";
import { CreateRoleDto } from "../auth/dto";

@Injectable()
export class RolesService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
  ) {}

  async listMatrix(tenantId: string) {
    await this.prisma.setTenantContext(tenantId);
    const [roles, permissions] = await Promise.all([
      this.prisma.role.findMany({
        where: { tenantId },
        include: { rolePermissions: { include: { permission: true } } },
        orderBy: { name: "asc" },
      }),
      this.prisma.permission.findMany({ orderBy: [{ module: "asc" }, { slug: "asc" }] }),
    ]);

    return {
      permissions: permissions.map((p) => ({
        id: p.id,
        slug: p.slug,
        module: p.module,
        description: p.description,
      })),
      roles: roles.map((role) => ({
        id: role.id,
        name: role.name,
        description: role.description,
        isSystemRole: role.isSystemRole,
        permissions: role.rolePermissions.map((rp) => rp.permission.slug),
      })),
    };
  }

  async createCustomRole(tenantId: string, actorId: string, dto: CreateRoleDto) {
    await this.prisma.setTenantContext(tenantId);
    if (!dto.name?.trim()) {
      throw new BadRequestException("Role name is required");
    }

    const role = await this.prisma.role.create({
      data: {
        tenantId,
        name: dto.name.trim(),
        description: dto.description,
        isSystemRole: false,
      },
    });

    if (dto.permissionSlugs?.length) {
      const permissions = await this.prisma.permission.findMany({
        where: { slug: { in: dto.permissionSlugs } },
      });
      await this.prisma.rolePermission.createMany({
        data: permissions.map((p) => ({ roleId: role.id, permissionId: p.id })),
        skipDuplicates: true,
      });
    }

    await this.audit.record({
      tenantId,
      actorId,
      eventType: "role.created",
      entityType: "role",
      entityId: role.id,
      payload: { name: role.name, permissionSlugs: dto.permissionSlugs ?? [] },
    });

    return this.listMatrix(tenantId);
  }
}
