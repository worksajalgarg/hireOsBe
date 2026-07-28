import {
  createParamDecorator,
  ExecutionContext,
  SetMetadata,
} from "@nestjs/common";
import { TenantScopedRequest } from "../common/tenant-context.middleware";

export const CurrentUser = createParamDecorator((_data: unknown, ctx: ExecutionContext) => {
  const req = ctx.switchToHttp().getRequest<TenantScopedRequest>();
  return {
    id: req.actorId,
    tenantId: req.tenantId,
    sessionId: req.sessionId,
    permissions: req.permissions ?? [],
    roleName: req.actorRole,
  };
});

export const TenantId = createParamDecorator((_data: unknown, ctx: ExecutionContext) => {
  return ctx.switchToHttp().getRequest<TenantScopedRequest>().tenantId;
});

export const PERMISSIONS_KEY = "required_permissions";
export const RequirePermissions = (...permissions: string[]) =>
  SetMetadata(PERMISSIONS_KEY, permissions);
