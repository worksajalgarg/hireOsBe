import { Module } from "@nestjs/common";
import { JobRolesController } from "./job-roles.controller";
import { JobRolesService } from "./job-roles.service";
import { AuditModule } from "../audit/audit.module";

/**
 * Job requisitions (hiring "roles" in the recruiter-workflow sense — NOT the
 * RBAC `Role` model, see docs/adr on job-role naming). Owns JD create
 * (paste/upload) -> ai-service parse -> structured requirements. Replaces
 * the former role-context/ stub module.
 */
@Module({
  imports: [AuditModule],
  controllers: [JobRolesController],
  providers: [JobRolesService],
  exports: [JobRolesService],
})
export class JobRolesModule {}
