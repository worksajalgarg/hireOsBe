import { Injectable, NestMiddleware } from "@nestjs/common";
import { NextFunction, Request, Response } from "express";

export interface TenantScopedRequest extends Request {
  tenantId?: string;
  actorId?: string;
  actorRole?: string;
}

/**
 * Reads tenant/actor identity off request headers and stamps it onto the
 * request object before any controller runs. This is the single point where
 * tenant isolation begins per PRD Section 8.1 ("tenant ID enforced in
 * application, database query, object path, cache and audit layers").
 *
 * Headers are a placeholder until session-based auth lands (apps/web auth
 * wiring, tracked separately) — once that exists, this middleware should
 * derive tenantId/actorId/actorRole from the verified session instead of
 * trusting client-supplied headers.
 */
@Injectable()
export class TenantContextMiddleware implements NestMiddleware {
  use(req: TenantScopedRequest, _res: Response, next: NextFunction) {
    req.tenantId = req.header("x-tenant-id") ?? undefined;
    req.actorId = req.header("x-actor-id") ?? undefined;
    req.actorRole = req.header("x-actor-role") ?? undefined;
    next();
  }
}
