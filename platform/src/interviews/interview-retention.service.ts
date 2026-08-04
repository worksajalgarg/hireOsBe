import { Injectable, Logger } from "@nestjs/common";
import { Cron, CronExpression } from "@nestjs/schedule";
import { PrismaService } from "../common/prisma.service";

/**
 * Deletes InterviewTranscript/InterviewSummary rows once they're older than
 * the owning tenant's TenantPolicy.retentionDays — see
 * docs/adr/0006-interview-transcript-storage.md. These rows must never
 * become a second, unmanaged place candidate PII lives outside the
 * retention window every other tenant data already respects.
 *
 * Runs per-tenant (not one global cutoff) since retentionDays varies per
 * tenant; pilot scale (a handful of tenants) makes a simple loop the right
 * tradeoff over a single cross-tenant SQL statement.
 */
@Injectable()
export class InterviewRetentionService {
  private readonly logger = new Logger(InterviewRetentionService.name);

  constructor(private readonly prisma: PrismaService) {}

  @Cron(CronExpression.EVERY_DAY_AT_MIDNIGHT)
  async cleanupExpiredTranscripts(): Promise<void> {
    const policies = await this.prisma.tenantPolicy.findMany();
    for (const policy of policies) {
      const cutoff = new Date(Date.now() - policy.retentionDays * 24 * 60 * 60 * 1000);
      const [transcripts, summaries] = await Promise.all([
        this.prisma.interviewTranscript.deleteMany({
          where: { tenantId: policy.tenantId, createdAt: { lt: cutoff } },
        }),
        this.prisma.interviewSummary.deleteMany({
          where: { tenantId: policy.tenantId, createdAt: { lt: cutoff } },
        }),
      ]);
      if (transcripts.count > 0 || summaries.count > 0) {
        this.logger.log(
          `Retention cleanup for tenant ${policy.tenantId}: removed ${transcripts.count} transcript(s), ${summaries.count} summary(ies) older than ${policy.retentionDays}d`,
        );
      }
    }
  }
}
