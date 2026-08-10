import { Injectable } from "@nestjs/common";
import { ThrottlerGuard } from "@nestjs/throttler";
import { TenantScopedRequest } from "./tenant-context.middleware";

/**
 * Rate-limits by tenantId instead of the default IP-based tracker — see
 * docs/adr/0006-interview-transcript-storage.md's Phase E section. The
 * app-wide generic ThrottlerModule.forRoot(...) (100 req/min per IP,
 * app.module.ts) still applies everywhere; this is a stricter, additional
 * limit for routes where a compromised *account* (not just a single IP)
 * spinning up unbounded requests is the actual identified risk — e.g.
 * interview-session creation, which each burns real LiveKit room +
 * dispatched-worker STT/LLM/TTS cost regardless of IP.
 *
 * Falls back to IP if tenantId isn't set (shouldn't happen on a route this
 * guard is applied to, since JwtAuthGuard — a global guard, so it always
 * runs first — populates it) rather than throwing, so a guard ordering
 * mistake fails safe (falls back to IP-based limiting) instead of 500ing.
 */
@Injectable()
export class TenantThrottlerGuard extends ThrottlerGuard {
  protected async getTracker(req: TenantScopedRequest): Promise<string> {
    return req.tenantId ?? req.ip ?? "unknown";
  }
}
