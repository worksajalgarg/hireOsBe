import { Injectable, NestMiddleware } from "@nestjs/common";
import { NextFunction, Request, Response } from "express";

export interface TenantScopedRequest extends Request {
  tenantId?: string;
  actorId?: string;
  actorRole?: string;
  sessionId?: string;
  permissions?: string[];
}

/**
 * Legacy header fallback for local bootstrap/scripts. JWT claims from
 * JwtAuthGuard overwrite these for authenticated `/api/v1` routes.
 */
@Injectable()
export class TenantContextMiddleware implements NestMiddleware {
  use(req: TenantScopedRequest, _res: Response, next: NextFunction) {
    if (!req.tenantId) {
      req.tenantId = req.header("x-tenant-id") ?? undefined;
    }
    if (!req.actorId) {
      req.actorId = req.header("x-actor-id") ?? undefined;
    }
    if (!req.actorRole) {
      req.actorRole = req.header("x-actor-role") ?? undefined;
    }
    next();
  }
}
