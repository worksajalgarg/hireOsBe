import { Injectable, OnModuleDestroy, OnModuleInit } from "@nestjs/common";
import { PrismaPg } from "@prisma/adapter-pg";
import { Prisma, PrismaClient } from "@prisma/client";
import pg from "pg";

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  constructor() {
    const rawUrl = process.env.DATABASE_URL || "";
    const cleanUrl = rawUrl
      .replace(/&?channel_binding=[^&]*/g, "")
      .replace(/&?sslmode=[^&]*/g, "")
      .replace(/\?$/, "");

    const pool = new pg.Pool({
      connectionString: cleanUrl,
      ssl: { rejectUnauthorized: false },
    });
    super({ adapter: new PrismaPg(pool) });
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

  /**
   * Execute tenant data access on one database connection with transaction-local RLS
   * context. This avoids session GUC values leaking across pooled connections.
   */
  async withTenant<T>(
    tenantId: string,
    operation: (tx: Prisma.TransactionClient) => Promise<T>,
  ): Promise<T> {
    return this.$transaction(async (tx) => {
      await tx.$executeRaw`SELECT set_config('app.current_tenant_id', ${tenantId}, true)`;
      return operation(tx);
    });
  }
}
