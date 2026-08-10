import { Injectable } from "@nestjs/common";
import { PrismaService } from "./prisma.service";
import {
  PERMISSION_META,
  PERMISSIONS,
  SYSTEM_ROLE_NAMES,
  SYSTEM_ROLE_PERMISSIONS,
} from "./permissions";

@Injectable()
export class RbacSeedService {
  constructor(private readonly prisma: PrismaService) {}

  async ensurePermissions() {
    for (const slug of Object.values(PERMISSIONS)) {
      const meta = PERMISSION_META[slug];
      await this.prisma.permission.upsert({
        where: { slug },
        create: { slug, module: meta.module, description: meta.description },
        update: { module: meta.module, description: meta.description },
      });
    }
  }

  /** Create Admin / Recruiter / Hiring Manager / Auditor roles + grants for a tenant. */
  async seedSystemRolesForTenant(tenantId: string) {
    await this.ensurePermissions();
    const permissions = await this.prisma.permission.findMany();
    const bySlug = new Map(permissions.map((p) => [p.slug, p.id]));

    for (const [roleName, slugs] of Object.entries(SYSTEM_ROLE_PERMISSIONS)) {
      const role = await this.prisma.role.upsert({
        where: { tenantId_name: { tenantId, name: roleName } },
        create: {
          tenantId,
          name: roleName,
          description: `${roleName} system role`,
          isSystemRole: true,
        },
        update: {},
      });

      for (const slug of slugs) {
        const permissionId = bySlug.get(slug);
        if (!permissionId) continue;
        await this.prisma.rolePermission.upsert({
          where: {
            roleId_permissionId: { roleId: role.id, permissionId },
          },
          create: { roleId: role.id, permissionId },
          update: {},
        });
      }
    }
  }

  async findSystemRoleId(tenantId: string, roleName: string = SYSTEM_ROLE_NAMES.Admin) {
    const role = await this.prisma.role.findUnique({
      where: { tenantId_name: { tenantId, name: roleName } },
    });
    return role?.id;
  }
}
