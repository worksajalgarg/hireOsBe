import {
  BadRequestException,
  Injectable,
  NotImplementedException,
  UnauthorizedException,
} from "@nestjs/common";
import { JwtService } from "@nestjs/jwt";
import * as argon2 from "argon2";
import { createHash, randomBytes } from "crypto";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";
import { SsoProvider } from "./sso.provider";
import {
  ACCESS_TOKEN_TTL_SECONDS,
  AuthJwtPayload,
  REFRESH_TOKEN_TTL_MS,
} from "./auth.types";
import {
  AcceptInviteDto,
  ForgotPasswordDto,
  LoginDto,
  ResetPasswordDto,
  SsoCallbackDto,
} from "./dto";

@Injectable()
export class AuthService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly jwt: JwtService,
    private readonly audit: AuditService,
    private readonly sso: SsoProvider,
  ) {}

  private hashToken(token: string) {
    return createHash("sha256").update(token).digest("hex");
  }

  private async loadMembershipContext(userId: string, tenantId?: string) {
    const memberships = await this.prisma.tenantUserRole.findMany({
      where: { userId },
      include: {
        role: {
          include: {
            rolePermissions: { include: { permission: true } },
          },
        },
        tenant: true,
        user: { include: { profile: true } },
      },
      orderBy: { assignedAt: "asc" },
    });

    if (memberships.length === 0) {
      throw new UnauthorizedException("User has no tenant memberships");
    }

    const membership =
      (tenantId ? memberships.find((m) => m.tenantId === tenantId) : undefined) ??
      memberships[0];

    if (!membership) {
      throw new UnauthorizedException("User is not a member of the requested tenant");
    }

    const permissions = membership.role.rolePermissions.map((rp) => rp.permission.slug);
    return { membership, permissions, user: membership.user, tenant: membership.tenant };
  }

  private async issueTokens(params: {
    userId: string;
    tenantId: string;
    roleName: string;
    permissions: string[];
    userAgent?: string;
    ipAddress?: string;
  }) {
    const refreshToken = randomBytes(48).toString("hex");
    const refreshTokenHash = this.hashToken(refreshToken);
    const expiresAt = new Date(Date.now() + REFRESH_TOKEN_TTL_MS);

    const session = await this.prisma.userSession.create({
      data: {
        userId: params.userId,
        tenantId: params.tenantId,
        refreshTokenHash,
        userAgent: params.userAgent,
        ipAddress: params.ipAddress,
        expiresAt,
      },
    });

    const payload: AuthJwtPayload = {
      sub: params.userId,
      tenantId: params.tenantId,
      sessionId: session.id,
      roleName: params.roleName,
      permissions: params.permissions,
    };

    const accessToken = await this.jwt.signAsync(payload, {
      secret: process.env.JWT_ACCESS_SECRET ?? "dev-access-secret-change-me",
      expiresIn: ACCESS_TOKEN_TTL_SECONDS,
    });

    return {
      accessToken,
      refreshToken,
      expiresIn: ACCESS_TOKEN_TTL_SECONDS,
      tokenType: "Bearer" as const,
      sessionId: session.id,
    };
  }

  async login(dto: LoginDto, meta: { userAgent?: string; ipAddress?: string }) {
    const user = await this.prisma.user.findUnique({ where: { email: dto.email.toLowerCase() } });
    if (!user?.passwordHash || user.status === "DISABLED") {
      throw new UnauthorizedException("Invalid email or password");
    }

    const valid = await argon2.verify(user.passwordHash, dto.password);
    if (!valid) {
      throw new UnauthorizedException("Invalid email or password");
    }

    if (user.isMfaEnabled) {
      throw new UnauthorizedException({
        code: "MFA_REQUIRED",
        message: "MFA verification required",
      });
    }

    const { membership, permissions, tenant } = await this.loadMembershipContext(
      user.id,
      dto.tenantId,
    );

    await this.prisma.user.update({
      where: { id: user.id },
      data: { lastLoginAt: new Date(), lastLoginIp: meta.ipAddress },
    });

    const tokens = await this.issueTokens({
      userId: user.id,
      tenantId: membership.tenantId,
      roleName: membership.role.name,
      permissions,
      userAgent: meta.userAgent,
      ipAddress: meta.ipAddress,
    });

    await this.audit.record({
      tenantId: membership.tenantId,
      actorId: user.id,
      eventType: "user.login",
      entityType: "user",
      entityId: user.id,
      payload: { sessionId: tokens.sessionId },
    });

    const profile = await this.prisma.userProfile.findUnique({ where: { userId: user.id } });

    return {
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
      expiresIn: tokens.expiresIn,
      tokenType: tokens.tokenType,
      user: {
        id: user.id,
        email: user.email,
        status: user.status,
        isMfaEnabled: user.isMfaEnabled,
        createdAt: user.createdAt.toISOString(),
        tenantId: membership.tenantId,
        roleName: membership.role.name,
        permissions,
        profile,
      },
      tenant: {
        id: tenant.id,
        name: tenant.name,
        domain: tenant.domain,
        logoUrl: tenant.logoUrl,
        settingsJson: tenant.settingsJson as Record<string, unknown>,
        createdAt: tenant.createdAt.toISOString(),
        updatedAt: tenant.updatedAt.toISOString(),
      },
    };
  }

  async refresh(refreshToken: string | undefined, meta: { userAgent?: string; ipAddress?: string }) {
    if (!refreshToken) {
      throw new UnauthorizedException("Missing refresh token");
    }

    const hash = this.hashToken(refreshToken);
    const session = await this.prisma.userSession.findFirst({
      where: {
        refreshTokenHash: hash,
        revokedAt: null,
        expiresAt: { gt: new Date() },
      },
    });

    if (!session) {
      throw new UnauthorizedException("Invalid refresh token");
    }

    await this.prisma.userSession.update({
      where: { id: session.id },
      data: { revokedAt: new Date() },
    });

    const { membership, permissions } = await this.loadMembershipContext(
      session.userId,
      session.tenantId,
    );

    const tokens = await this.issueTokens({
      userId: session.userId,
      tenantId: membership.tenantId,
      roleName: membership.role.name,
      permissions,
      userAgent: meta.userAgent,
      ipAddress: meta.ipAddress,
    });

    return {
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
      expiresIn: tokens.expiresIn,
      tokenType: tokens.tokenType,
    };
  }

  async logout(sessionId?: string, actorId?: string, tenantId?: string) {
    if (sessionId) {
      await this.prisma.userSession.updateMany({
        where: { id: sessionId, revokedAt: null },
        data: { revokedAt: new Date() },
      });
    }
    if (actorId && tenantId) {
      await this.audit.record({
        tenantId,
        actorId,
        eventType: "user.logout",
        entityType: "user",
        entityId: actorId,
        payload: { sessionId },
      });
    }
    return { ok: true };
  }

  async ssoCallback(dto: SsoCallbackDto, meta: { userAgent?: string; ipAddress?: string }) {
    const identity = await this.sso.exchangeCode(dto.provider, dto.code);
    let user = await this.prisma.user.findFirst({
      where: {
        OR: [
          { ssoProvider: identity.provider, ssoId: identity.ssoId },
          { email: identity.email.toLowerCase() },
        ],
      },
    });

    if (!user) {
      throw new UnauthorizedException(
        "No HireOS account is linked to this SSO identity. Request access first.",
      );
    }

    user = await this.prisma.user.update({
      where: { id: user.id },
      data: {
        ssoProvider: identity.provider,
        ssoId: identity.ssoId,
        lastLoginAt: new Date(),
        lastLoginIp: meta.ipAddress,
      },
    });

    const { membership, permissions, tenant } = await this.loadMembershipContext(
      user.id,
      dto.tenantId,
    );

    const tokens = await this.issueTokens({
      userId: user.id,
      tenantId: membership.tenantId,
      roleName: membership.role.name,
      permissions,
      userAgent: meta.userAgent,
      ipAddress: meta.ipAddress,
    });

    return {
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken,
      expiresIn: tokens.expiresIn,
      tokenType: tokens.tokenType,
      user: {
        id: user.id,
        email: user.email,
        status: user.status,
        isMfaEnabled: user.isMfaEnabled,
        createdAt: user.createdAt.toISOString(),
        tenantId: membership.tenantId,
        roleName: membership.role.name,
        permissions,
      },
      tenant: {
        id: tenant.id,
        name: tenant.name,
        domain: tenant.domain,
        createdAt: tenant.createdAt.toISOString(),
      },
    };
  }

  async forgotPassword(dto: ForgotPasswordDto) {
    const user = await this.prisma.user.findUnique({
      where: { email: dto.email.toLowerCase() },
    });
    // Always succeed to avoid account enumeration
    if (!user) {
      return { ok: true };
    }

    const token = randomBytes(32).toString("hex");
    await this.prisma.passwordResetToken.create({
      data: {
        userId: user.id,
        tokenHash: this.hashToken(token),
        expiresAt: new Date(Date.now() + 60 * 60 * 1000),
      },
    });

    // Dev console adapter — replace with email provider later
    console.log(`[auth] password reset token for ${user.email}: ${token}`);

    const membership = await this.prisma.tenantUserRole.findFirst({ where: { userId: user.id } });
    if (membership) {
      await this.audit.record({
        tenantId: membership.tenantId,
        actorId: user.id,
        eventType: "user.password_reset_requested",
        entityType: "user",
        entityId: user.id,
        payload: {},
      });
    }

    return { ok: true, ...(process.env.NODE_ENV !== "production" ? { devToken: token } : {}) };
  }

  async resetPassword(dto: ResetPasswordDto) {
    const hash = this.hashToken(dto.token);
    const record = await this.prisma.passwordResetToken.findFirst({
      where: {
        tokenHash: hash,
        usedAt: null,
        expiresAt: { gt: new Date() },
      },
    });
    if (!record) {
      throw new BadRequestException("Invalid or expired reset token");
    }

    const passwordHash = await argon2.hash(dto.password);
    await this.prisma.$transaction([
      this.prisma.user.update({
        where: { id: record.userId },
        data: { passwordHash },
      }),
      this.prisma.passwordResetToken.update({
        where: { id: record.id },
        data: { usedAt: new Date() },
      }),
      this.prisma.userSession.updateMany({
        where: { userId: record.userId, revokedAt: null },
        data: { revokedAt: new Date() },
      }),
    ]);

    return { ok: true };
  }

  async mfaVerify() {
    throw new NotImplementedException("TOTP MFA enrollment is not enabled yet");
  }

  async acceptInvite(dto: AcceptInviteDto) {
    const hash = this.hashToken(dto.token);
    const invitation = await this.prisma.tenantInvitation.findFirst({
      where: {
        tokenHash: hash,
        status: "PENDING",
        expiresAt: { gt: new Date() },
      },
    });
    if (!invitation) {
      throw new BadRequestException("Invalid or expired invitation");
    }

    const passwordHash = await argon2.hash(dto.password);
    const email = invitation.email.toLowerCase();

    const result = await this.prisma.$transaction(async (tx) => {
      let user = await tx.user.findUnique({ where: { email } });
      if (!user) {
        user = await tx.user.create({
          data: {
            email,
            passwordHash,
            status: "ACTIVE",
            profile: {
              create: {
                firstName: dto.firstName,
                lastName: dto.lastName,
              },
            },
          },
        });
      } else {
        user = await tx.user.update({
          where: { id: user.id },
          data: { passwordHash, status: "ACTIVE" },
        });
        await tx.userProfile.upsert({
          where: { userId: user.id },
          create: {
            userId: user.id,
            firstName: dto.firstName,
            lastName: dto.lastName,
          },
          update: {
            firstName: dto.firstName ?? undefined,
            lastName: dto.lastName ?? undefined,
          },
        });
      }

      await tx.tenantUserRole.upsert({
        where: {
          tenantId_userId: { tenantId: invitation.tenantId, userId: user.id },
        },
        create: {
          tenantId: invitation.tenantId,
          userId: user.id,
          roleId: invitation.roleId,
        },
        update: { roleId: invitation.roleId },
      });

      await tx.tenantInvitation.update({
        where: { id: invitation.id },
        data: { status: "ACCEPTED", acceptedAt: new Date() },
      });

      return user;
    });

    return { ok: true, userId: result.id, tenantId: invitation.tenantId };
  }
}
