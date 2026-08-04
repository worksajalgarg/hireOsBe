import {
  CanActivate,
  ExecutionContext,
  Injectable,
  UnauthorizedException,
} from "@nestjs/common";
import { Reflector } from "@nestjs/core";
import { JwtService } from "@nestjs/jwt";
import { IS_PUBLIC_KEY } from "./public.decorator";
import { AuthJwtPayload } from "./auth.types";
import { TenantScopedRequest } from "../common/tenant-context.middleware";
import { PrismaService } from "../common/prisma.service";

@Injectable()
export class JwtAuthGuard implements CanActivate {
  constructor(
    private readonly jwt: JwtService,
    private readonly reflector: Reflector,
    private readonly prisma: PrismaService,
  ) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);
    if (isPublic) return true;

    const request = context.switchToHttp().getRequest<TenantScopedRequest>();
    const header = request.headers.authorization;
    if (!header?.startsWith("Bearer ")) {
      throw new UnauthorizedException("Missing access token");
    }

    const token = header.slice("Bearer ".length);
    let payload: AuthJwtPayload;
    try {
      payload = await this.jwt.verifyAsync<AuthJwtPayload>(token);
    } catch {
      throw new UnauthorizedException("Invalid or expired access token");
    }

    request.actorId = payload.sub;
    request.tenantId = payload.tenantId;
    request.sessionId = payload.sessionId;
    request.permissions = payload.permissions ?? [];
    request.actorRole = payload.roleName;

    await this.prisma.setTenantContext(payload.tenantId);
    return true;
  }
}
