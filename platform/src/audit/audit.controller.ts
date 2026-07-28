import { Controller, Get } from "@nestjs/common";
import { ApiBearerAuth, ApiTags } from "@nestjs/swagger";
import { UserRole } from "../common/types";
import { Roles } from "../common/roles.decorator";
import { RequirePermissions, CurrentUser } from "../auth/auth.decorators";
import { AuditService } from "./audit.service";
import { PERMISSIONS } from "../common/permissions";

@ApiTags("audit")
@ApiBearerAuth()
@Controller("audit-events")
export class AuditController {
  constructor(private readonly auditService: AuditService) {}

  @Get()
  @Roles(UserRole.Admin, UserRole.Auditor)
  @RequirePermissions(PERMISSIONS.AUDIT_READ)
  async list(@CurrentUser() user: { tenantId: string }) {
    return this.auditService.listForTenant(user.tenantId);
  }
}
