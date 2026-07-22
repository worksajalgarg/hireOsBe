import { Module } from "@nestjs/common";
import { AuditModule } from "../audit/audit.module";
import { TenantService } from "./tenant.service";
import { TenantController } from "./tenant.controller";

@Module({
  imports: [AuditModule],
  providers: [TenantService],
  controllers: [TenantController],
  exports: [TenantService],
})
export class TenantModule {}
