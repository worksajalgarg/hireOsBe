import { Global, Module } from "@nestjs/common";
import { PrismaService } from "./prisma.service";
import { RedisService } from "./redis.service";
import { TenantContextService } from "./tenant-context.service";
import { RbacSeedService } from "./rbac-seed.service";
import { ObjectStorageService } from "./storage/object-storage.service";
import { AiServiceClient } from "./http/ai-service.client";

@Global()
@Module({
  providers: [
    PrismaService,
    RedisService,
    TenantContextService,
    RbacSeedService,
    ObjectStorageService,
    AiServiceClient,
  ],
  exports: [
    PrismaService,
    RedisService,
    TenantContextService,
    RbacSeedService,
    ObjectStorageService,
    AiServiceClient,
  ],
})
export class CommonModule {}
