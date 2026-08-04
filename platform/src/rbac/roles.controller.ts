import { Body, Controller, Get, Post } from "@nestjs/common";
import { ApiBearerAuth, ApiTags } from "@nestjs/swagger";
import { RolesService } from "./roles.service";
import { CurrentUser, RequirePermissions } from "../auth/auth.decorators";
import { CreateRoleDto } from "../auth/dto";
import { PERMISSIONS } from "../common/permissions";

@ApiTags("roles")
@ApiBearerAuth()
@Controller("roles")
export class RolesController {
  constructor(private readonly rolesService: RolesService) {}

  @Get()
  @RequirePermissions(PERMISSIONS.ROLES_READ)
  async list(@CurrentUser() user: { tenantId: string }) {
    return this.rolesService.listMatrix(user.tenantId);
  }

  @Post()
  @RequirePermissions(PERMISSIONS.ROLES_WRITE)
  async create(
    @CurrentUser() user: { id: string; tenantId: string },
    @Body() dto: CreateRoleDto,
  ) {
    return this.rolesService.createCustomRole(user.tenantId, user.id, dto);
  }
}
