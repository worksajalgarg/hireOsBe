import { Controller, Get } from "@nestjs/common";
import { UserRole } from "../common/types";
import { Roles } from "../common/roles.decorator";
import { TenantContextService } from "../common/tenant-context.service";
import { AuditService } from "./audit.service";

@Controller("audit-events")
export class AuditController {
  constructor(
    private readonly auditService: AuditService,
    private readonly tenantContext: TenantContextService,
  ) {}

  @Get()
  @Roles(UserRole.Admin, UserRole.Auditor)
  async list() {
    return this.auditService.listForTenant(this.tenantContext.getTenantId());
  }
}
