import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
} from "@nestjs/common";
import { PrismaService } from "../common/prisma.service";
import { TenantScopedRequest } from "../common/tenant-context.middleware";

@Injectable()
export class TenantAccessGuard implements CanActivate {
  constructor(private readonly prisma: PrismaService) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest<TenantScopedRequest>();
    if (!request.actorId || !request.tenantId) {
      throw new ForbiddenException("Tenant context required");
    }

    const membership = await this.prisma.tenantUserRole.findUnique({
      where: {
        tenantId_userId: {
          tenantId: request.tenantId,
          userId: request.actorId,
        },
      },
    });

    if (!membership) {
      throw new ForbiddenException("User is not a member of this tenant");
    }
    return true;
  }
}
