import { CanActivate, ExecutionContext, ForbiddenException, Injectable } from "@nestjs/common";
import { Reflector } from "@nestjs/core";
import { UserRole } from "./types";
import { ROLES_KEY } from "./roles.decorator";
import { TenantScopedRequest } from "./tenant-context.middleware";
import { LEGACY_ROLE_TO_SYSTEM_NAME } from "./permissions";

/**
 * Temporary bridge: maps JWT roleName (e.g. "Admin") or legacy actorRole
 * ("admin") against @Roles(...). Prefer @RequirePermissions going forward.
 */
@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const requiredRoles = this.reflector.getAllAndOverride<UserRole[] | undefined>(ROLES_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);

    if (!requiredRoles || requiredRoles.length === 0) {
      return true;
    }

    const request = context.switchToHttp().getRequest<TenantScopedRequest>();
    const actorRole = request.actorRole;
    if (!actorRole) {
      throw new ForbiddenException("Role 'unknown' is not permitted to perform this action");
    }

    const normalized = actorRole.toLowerCase().replace(/\s+/g, "_");
    const allowed = requiredRoles.some((role) => {
      const systemName = LEGACY_ROLE_TO_SYSTEM_NAME[role]?.toLowerCase();
      return (
        role === actorRole ||
        role === normalized ||
        systemName === actorRole.toLowerCase() ||
        LEGACY_ROLE_TO_SYSTEM_NAME[normalized] === actorRole
      );
    });

    if (!allowed) {
      throw new ForbiddenException(
        `Role '${actorRole}' is not permitted to perform this action`,
      );
    }

    return true;
  }
}
