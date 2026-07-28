import { Global, Module } from "@nestjs/common";
import { PrismaService } from "./prisma.service";
import { TenantContextService } from "./tenant-context.service";
import { RbacSeedService } from "./rbac-seed.service";
import { ObjectStorageService } from "./storage/object-storage.service";

@Global()
@Module({
  providers: [PrismaService, TenantContextService, RbacSeedService, ObjectStorageService],
  exports: [PrismaService, TenantContextService, RbacSeedService, ObjectStorageService],
})
export class CommonModule {}
