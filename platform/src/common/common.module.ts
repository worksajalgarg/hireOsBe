import { Global, Module } from "@nestjs/common";
import { PrismaService } from "./prisma.service";
import { RedisService } from "./redis.service";
import { TenantContextService } from "./tenant-context.service";
import { RbacSeedService } from "./rbac-seed.service";

@Global()
@Module({
  providers: [PrismaService, RedisService, TenantContextService, RbacSeedService],
  exports: [PrismaService, RedisService, TenantContextService, RbacSeedService],
})
export class CommonModule {}
