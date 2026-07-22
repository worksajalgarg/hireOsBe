import { Injectable, Scope, UnauthorizedException } from "@nestjs/common";
import { Inject } from "@nestjs/common";
import { REQUEST } from "@nestjs/core";
import type { TenantScopedRequest } from "./tenant-context.middleware";

/**
 * Request-scoped accessor for the current tenant/actor. Every service that
 * touches tenant-owned data must go through this instead of reading headers
 * or the request directly, so tenant scoping is enforced in exactly one
 * place and cannot be silently bypassed by a new module.
 */
@Injectable({ scope: Scope.REQUEST })
export class TenantContextService {
  constructor(@Inject(REQUEST) private readonly request: TenantScopedRequest) {}

  getTenantId(): string {
    if (!this.request.tenantId) {
      throw new UnauthorizedException("Missing tenant context");
    }
    return this.request.tenantId;
  }

  getActorId(): string {
    if (!this.request.actorId) {
      throw new UnauthorizedException("Missing actor context");
    }
    return this.request.actorId;
  }

  getActorRole(): string | undefined {
    return this.request.actorRole;
  }
}
