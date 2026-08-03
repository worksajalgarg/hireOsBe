import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from "@nestjs/common";
import { timingSafeEqual } from "crypto";

/**
 * The one, general-purpose trust anchor between ai-service and platform —
 * see docs/adr/0006-interview-transcript-storage.md. ai-service is not an
 * authenticated end-user, so it can't carry a user JWT; routes behind this
 * guard must also be marked @Public() to bypass the global JwtAuthGuard,
 * which otherwise rejects any request without a valid user token before
 * this guard ever runs.
 *
 * Deliberately the single shared secret for all ai-service->platform calls
 * (not one per feature) — reuse this guard for any future internal route
 * rather than minting a new secret per endpoint.
 */
@Injectable()
export class InternalServiceGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const secret = process.env.INTERNAL_SERVICE_SECRET;
    if (!secret) {
      throw new UnauthorizedException("INTERNAL_SERVICE_SECRET is not configured");
    }

    const request = context.switchToHttp().getRequest();
    const header: string | undefined = request.headers.authorization;
    if (!header?.startsWith("Bearer ")) {
      throw new UnauthorizedException("Missing internal service credentials");
    }

    const provided = Buffer.from(header.slice("Bearer ".length));
    const expected = Buffer.from(secret);
    if (provided.length !== expected.length || !timingSafeEqual(provided, expected)) {
      throw new UnauthorizedException("Invalid internal service credentials");
    }

    return true;
  }
}
