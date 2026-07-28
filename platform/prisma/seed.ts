/**
 * Dev bootstrap: creates a demo tenant + admin user.
 * Usage: npx tsx prisma/seed.ts
 */
import "dotenv/config";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@prisma/client";
import * as argon2 from "argon2";
import {
  PERMISSION_META,
  PERMISSIONS,
  SYSTEM_ROLE_NAMES,
  SYSTEM_ROLE_PERMISSIONS,
} from "../src/common/permissions";

const prisma = new PrismaClient({
  adapter: new PrismaPg({ connectionString: process.env.DATABASE_URL }),
});

async function seedPermissions() {
  for (const slug of Object.values(PERMISSIONS)) {
    const meta = PERMISSION_META[slug];
    await prisma.permission.upsert({
      where: { slug },
      create: { slug, module: meta.module, description: meta.description },
      update: { module: meta.module, description: meta.description },
    });
  }
}

async function seedSystemRoles(tenantId: string) {
  const permissions = await prisma.permission.findMany();
  const bySlug = new Map(permissions.map((p) => [p.slug, p.id]));

  for (const [roleName, slugs] of Object.entries(SYSTEM_ROLE_PERMISSIONS)) {
    const role = await prisma.role.upsert({
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
      await prisma.rolePermission.upsert({
        where: { roleId_permissionId: { roleId: role.id, permissionId } },
        create: { roleId: role.id, permissionId },
        update: {},
      });
    }
  }
}

async function main() {
  const email = (process.env.SEED_ADMIN_EMAIL ?? "admin@hireos.local").toLowerCase();
  const password = process.env.SEED_ADMIN_PASSWORD ?? "Password123!";

  await seedPermissions();

  const tenant = await prisma.tenant.upsert({
    where: { domain: "acme.hireos.local" },
    create: {
      name: "Acme Hiring",
      domain: "acme.hireos.local",
      settingsJson: { primaryColor: "#0A1F33" },
      policies: { create: {} },
    },
    update: {},
  });

  await seedSystemRoles(tenant.id);

  const passwordHash = await argon2.hash(password);
  const user = await prisma.user.upsert({
    where: { email },
    create: {
      email,
      passwordHash,
      status: "ACTIVE",
      profile: {
        create: {
          firstName: "Ada",
          lastName: "Admin",
          jobTitle: "Platform Admin",
        },
      },
    },
    update: { passwordHash, status: "ACTIVE" },
  });

  const adminRole = await prisma.role.findUniqueOrThrow({
    where: { tenantId_name: { tenantId: tenant.id, name: SYSTEM_ROLE_NAMES.Admin } },
  });

  await prisma.tenantUserRole.upsert({
    where: { tenantId_userId: { tenantId: tenant.id, userId: user.id } },
    create: {
      tenantId: tenant.id,
      userId: user.id,
      roleId: adminRole.id,
    },
    update: { roleId: adminRole.id },
  });

  console.log("Seed complete:");
  console.log(`  tenant: ${tenant.name} (${tenant.id})`);
  console.log(`  admin:  ${email} / ${password}`);
}

main()
  .catch((err) => {
    console.error(err);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
