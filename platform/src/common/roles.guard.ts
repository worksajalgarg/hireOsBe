import { CanActivate, ExecutionContext, ForbiddenException, Injectable } from "@nestjs/common";
import { Reflector } from "@nestjs/core";
import { UserRole } from "./types";
import { ROLES_KEY } from "./roles.decorator";
import { TenantScopedRequest } from "./tenant-context.middleware";

/**
 * Least-privilege enforcement per FR-102: a route decorated with @Roles(...)
 * rejects any actor whose role is not in the allowed set. Routes with no
 * @Roles decorator are left to the controller to reason about explicitly.
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
    const actorRole = request.actorRole as UserRole | undefined;

    if (!actorRole || !requiredRoles.includes(actorRole)) {
      throw new ForbiddenException(
        `Role '${actorRole ?? "unknown"}' is not permitted to perform this action`,
      );
    }

    return true;
  }
}
