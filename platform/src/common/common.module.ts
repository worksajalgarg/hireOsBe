import { Global, Module } from "@nestjs/common";
import { PrismaService } from "./prisma.service";
import { TenantContextService } from "./tenant-context.service";
import { RbacSeedService } from "./rbac-seed.service";

@Global()
@Module({
  providers: [PrismaService, TenantContextService, RbacSeedService],
  exports: [PrismaService, TenantContextService, RbacSeedService],
})
export class CommonModule {}
