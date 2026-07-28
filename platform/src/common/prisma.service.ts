import { Injectable, OnModuleDestroy, OnModuleInit } from "@nestjs/common";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@prisma/client";

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  constructor() {
    // Prisma 7: PrismaClient requires an explicit driver adapter — the
    // connection URL is no longer read from schema.prisma at runtime.
    super({ adapter: new PrismaPg({ connectionString: process.env.DATABASE_URL }) });
  }

  async onModuleInit() {
    await this.$connect();
  }

  async onModuleDestroy() {
    await this.$disconnect();
  }

  /**
   * Sets Postgres GUC used by RLS policies. Session-scoped (is_local=false)
   * so it applies to subsequent queries on this pooled connection. See ADR 0004.
   */
  async setTenantContext(tenantId: string | null) {
    const value = tenantId ?? "";
    await this.$executeRaw`SELECT set_config('app.current_tenant_id', ${value}, false)`;
  }
}
