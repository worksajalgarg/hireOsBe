import {
  BadRequestException,
  Injectable,
  NotFoundException,
} from "@nestjs/common";
import { createHash, randomBytes } from "crypto";
import { Prisma } from "@prisma/client";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";
import { ChangePasswordDto, UpdateProfileDto } from "../auth/dto";
import * as argon2 from "argon2";
import { LEGACY_ROLE_TO_SYSTEM_NAME } from "../common/permissions";

@Injectable()
export class UsersService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly auditService: AuditService,
  ) {}

  private hashToken(token: string) {
    return createHash("sha256").update(token).digest("hex");
  }

  async getMe(userId: string, tenantId: string) {
    await this.prisma.setTenantContext(tenantId);
    const membership = await this.prisma.tenantUserRole.findUnique({
      where: { tenantId_userId: { tenantId, userId } },
      include: {
        role: {
          include: { rolePermissions: { include: { permission: true } } },
        },
        tenant: true,
        user: { include: { profile: true } },
      },
    });
    if (!membership) {
      throw new NotFoundException("Membership not found");
    }

    const permissions = membership.role.rolePermissions.map((rp) => rp.permission.slug);
    return {
      id: membership.user.id,
      email: membership.user.email,
      status: membership.user.status,
      isMfaEnabled: membership.user.isMfaEnabled,
      createdAt: membership.user.createdAt.toISOString(),
      tenantId,
      roleName: membership.role.name,
      roleId: membership.roleId,
      permissions,
      profile: membership.user.profile,
      tenant: {
        id: membership.tenant.id,
        name: membership.tenant.name,
        domain: membership.tenant.domain,
        logoUrl: membership.tenant.logoUrl,
        createdAt: membership.tenant.createdAt.toISOString(),
      },
    };
  }

  async updateProfile(userId: string, dto: UpdateProfileDto) {
    const profile = await this.prisma.userProfile.upsert({
      where: { userId },
      create: {
        userId,
        firstName: dto.firstName,
        lastName: dto.lastName,
        phone: dto.phone,
        jobTitle: dto.jobTitle,
        avatarUrl: dto.avatarUrl,
        preferencesJson: (dto.preferencesJson ?? {}) as Prisma.InputJsonValue,
      },
      update: {
        firstName: dto.firstName,
        lastName: dto.lastName,
        phone: dto.phone,
        jobTitle: dto.jobTitle,
        avatarUrl: dto.avatarUrl,
        preferencesJson:
          dto.preferencesJson === undefined
            ? undefined
            : (dto.preferencesJson as Prisma.InputJsonValue),
      },
    });
    return profile;
  }

  async changePassword(userId: string, dto: ChangePasswordDto) {
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    if (!user?.passwordHash) {
      throw new BadRequestException("Password login is not configured for this account");
    }
    const ok = await argon2.verify(user.passwordHash, dto.currentPassword);
    if (!ok) {
      throw new BadRequestException("Current password is incorrect");
    }
    const passwordHash = await argon2.hash(dto.newPassword);
    await this.prisma.user.update({
      where: { id: userId },
      data: { passwordHash },
    });
    return { ok: true };
  }

  async listMembers(tenantId: string) {
    await this.prisma.setTenantContext(tenantId);
    const rows = await this.prisma.tenantUserRole.findMany({
      where: { tenantId },
      include: {
        user: { include: { profile: true } },
        role: true,
      },
      orderBy: { assignedAt: "asc" },
    });

    return rows.map((row) => ({
      userId: row.userId,
      email: row.user.email,
      status: row.user.status,
      roleId: row.roleId,
      roleName: row.role.name,
      firstName: row.user.profile?.firstName,
      lastName: row.user.profile?.lastName,
      joinedAt: row.assignedAt.toISOString(),
    }));
  }

  async inviteMember(params: {
    tenantId: string;
    email: string;
    roleId: string;
    actorId: string;
  }) {
    await this.prisma.setTenantContext(params.tenantId);
    const role = await this.prisma.role.findFirst({
      where: { id: params.roleId, tenantId: params.tenantId },
    });
    if (!role) {
      throw new NotFoundException("Role not found in tenant");
    }

    const email = params.email.toLowerCase();
    let user = await this.prisma.user.findUnique({ where: { email } });
    if (!user) {
      user = await this.prisma.user.create({
        data: {
          email,
          status: "INVITED",
          profile: { create: {} },
        },
      });
    }

    const token = randomBytes(32).toString("hex");
    const invitation = await this.prisma.tenantInvitation.create({
      data: {
        tenantId: params.tenantId,
        email,
        roleId: params.roleId,
        tokenHash: this.hashToken(token),
        invitedBy: params.actorId,
        expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000),
      },
    });

    console.log(`[auth] invite token for ${email}: ${token}`);

    await this.auditService.record({
      tenantId: params.tenantId,
      actorId: params.actorId,
      eventType: "user.invited",
      entityType: "user",
      entityId: user.id,
      payload: { email, roleId: params.roleId, invitationId: invitation.id },
    });

    return {
      invitationId: invitation.id,
      email,
      roleId: params.roleId,
      ...(process.env.NODE_ENV !== "production" ? { devToken: token } : {}),
    };
  }

  /** Legacy invite used by POST /users — maps UserRole enum to system role name. */
  async invite(params: {
    tenantId: string;
    email: string;
    role: string;
    actorId: string;
  }) {
    const roleName = LEGACY_ROLE_TO_SYSTEM_NAME[params.role] ?? params.role;
    const role = await this.prisma.role.findUnique({
      where: { tenantId_name: { tenantId: params.tenantId, name: roleName } },
    });
    if (!role) {
      throw new NotFoundException(`Role ${roleName} not found`);
    }
    return this.inviteMember({
      tenantId: params.tenantId,
      email: params.email,
      roleId: role.id,
      actorId: params.actorId,
    });
  }

  async changeMemberRole(params: {
    tenantId: string;
    userId: string;
    roleId: string;
    actorId: string;
  }) {
    await this.prisma.setTenantContext(params.tenantId);
    const role = await this.prisma.role.findFirst({
      where: { id: params.roleId, tenantId: params.tenantId },
    });
    if (!role) {
      throw new NotFoundException("Role not found");
    }

    const membership = await this.prisma.tenantUserRole.update({
      where: {
        tenantId_userId: { tenantId: params.tenantId, userId: params.userId },
      },
      data: { roleId: params.roleId },
    });

    await this.auditService.record({
      tenantId: params.tenantId,
      actorId: params.actorId,
      eventType: "user.role_changed",
      entityType: "user",
      entityId: params.userId,
      payload: { newRoleId: params.roleId, newRoleName: role.name },
    });

    return membership;
  }

  async changeRole(params: {
    tenantId: string;
    userId: string;
    role: string;
    actorId: string;
  }) {
    const roleName = LEGACY_ROLE_TO_SYSTEM_NAME[params.role] ?? params.role;
    const role = await this.prisma.role.findUnique({
      where: { tenantId_name: { tenantId: params.tenantId, name: roleName } },
    });
    if (!role) {
      throw new NotFoundException(`Role ${roleName} not found`);
    }
    return this.changeMemberRole({
      tenantId: params.tenantId,
      userId: params.userId,
      roleId: role.id,
      actorId: params.actorId,
    });
  }

  async removeMember(params: { tenantId: string; userId: string; actorId: string }) {
    await this.prisma.setTenantContext(params.tenantId);
    await this.prisma.tenantUserRole.delete({
      where: {
        tenantId_userId: { tenantId: params.tenantId, userId: params.userId },
      },
    });
    await this.prisma.userSession.updateMany({
      where: { tenantId: params.tenantId, userId: params.userId, revokedAt: null },
      data: { revokedAt: new Date() },
    });
    await this.auditService.record({
      tenantId: params.tenantId,
      actorId: params.actorId,
      eventType: "user.removed",
      entityType: "user",
      entityId: params.userId,
      payload: {},
    });
    return { ok: true };
  }

  async listForTenant(tenantId: string) {
    return this.listMembers(tenantId);
  }
}
