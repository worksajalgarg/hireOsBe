import { Injectable, OnModuleDestroy, OnModuleInit } from "@nestjs/common";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@prisma/client";
import pg from "pg";

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  constructor() {
    const rawUrl = process.env.DATABASE_URL || "";
    const cleanUrl = rawUrl
      .replace(/&?channel_binding=[^&]*/g, "")
      .replace(/&?sslmode=[^&]*/g, "")
      .replace(/\?$/, "");

    // Local Postgres (docker-compose) doesn't support TLS at all; Neon
    // (remote dev) requires it. Skip it only for loopback hosts so this
    // still defaults safely to "on" everywhere else.
    const isLocalHost = /^(localhost|127\.0\.0\.1)$/.test(new URL(cleanUrl).hostname);
    const pool = new pg.Pool({
      connectionString: cleanUrl,
      ssl: isLocalHost ? false : { rejectUnauthorized: false },
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
}
