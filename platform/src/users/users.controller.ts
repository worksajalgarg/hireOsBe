import { Body, Controller, Get, Param, Patch, Post } from "@nestjs/common";
import { UserRole } from "../common/types";
import { Roles } from "../common/roles.decorator";
import { TenantContextService } from "../common/tenant-context.service";
import { UsersService } from "./users.service";

interface InviteUserDto {
  email: string;
  role: UserRole;
}

interface ChangeRoleDto {
  role: UserRole;
}

@Controller("users")
export class UsersController {
  constructor(
    private readonly usersService: UsersService,
    private readonly tenantContext: TenantContextService,
  ) {}

  @Post()
  @Roles(UserRole.Admin)
  async invite(@Body() dto: InviteUserDto) {
    return this.usersService.invite({
      tenantId: this.tenantContext.getTenantId(),
      email: dto.email,
      role: dto.role,
      actorId: this.tenantContext.getActorId(),
    });
  }

  @Get()
  @Roles(UserRole.Admin, UserRole.Auditor)
  async list() {
    return this.usersService.listForTenant(this.tenantContext.getTenantId());
  }

  @Patch(":id/role")
  @Roles(UserRole.Admin)
  async changeRole(@Param("id") id: string, @Body() dto: ChangeRoleDto) {
    return this.usersService.changeRole({
      tenantId: this.tenantContext.getTenantId(),
      userId: id,
      role: dto.role,
      actorId: this.tenantContext.getActorId(),
    });
  }
}
