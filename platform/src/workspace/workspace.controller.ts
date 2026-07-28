import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Patch,
  Post,
} from "@nestjs/common";
import { ApiBearerAuth, ApiTags } from "@nestjs/swagger";
import { TenantService } from "../tenant/tenant.service";
import { UsersService } from "../users/users.service";
import { CurrentUser, RequirePermissions } from "../auth/auth.decorators";
import { InviteMemberDto, UpdateMemberRoleDto, UpdateWorkspaceSettingsDto } from "../auth/dto";
import { PERMISSIONS } from "../common/permissions";

@ApiTags("workspace")
@ApiBearerAuth()
@Controller("workspace")
export class WorkspaceController {
  constructor(
    private readonly tenantService: TenantService,
    private readonly usersService: UsersService,
  ) {}

  @Get("settings")
  @RequirePermissions(PERMISSIONS.WORKSPACE_SETTINGS_READ)
  async getSettings(@CurrentUser() user: { tenantId: string }) {
    return this.tenantService.getSettings(user.tenantId);
  }

  @Patch("settings")
  @RequirePermissions(PERMISSIONS.WORKSPACE_SETTINGS_WRITE)
  async updateSettings(
    @CurrentUser() user: { id: string; tenantId: string },
    @Body() dto: UpdateWorkspaceSettingsDto,
  ) {
    return this.tenantService.updateSettings(user.tenantId, user.id, dto);
  }

  @Get("members")
  @RequirePermissions(PERMISSIONS.MEMBERS_READ)
  async listMembers(@CurrentUser() user: { tenantId: string }) {
    return this.usersService.listMembers(user.tenantId);
  }

  @Post("members/invite")
  @RequirePermissions(PERMISSIONS.MEMBERS_INVITE)
  async invite(
    @CurrentUser() user: { id: string; tenantId: string },
    @Body() dto: InviteMemberDto,
  ) {
    return this.usersService.inviteMember({
      tenantId: user.tenantId,
      email: dto.email,
      roleId: dto.roleId,
      actorId: user.id,
    });
  }

  @Patch("members/:userId/role")
  @RequirePermissions(PERMISSIONS.MEMBERS_ROLE_WRITE)
  async changeRole(
    @CurrentUser() user: { id: string; tenantId: string },
    @Param("userId") userId: string,
    @Body() dto: UpdateMemberRoleDto,
  ) {
    return this.usersService.changeMemberRole({
      tenantId: user.tenantId,
      userId,
      roleId: dto.roleId,
      actorId: user.id,
    });
  }

  @Delete("members/:userId")
  @RequirePermissions(PERMISSIONS.MEMBERS_REMOVE)
  async remove(
    @CurrentUser() user: { id: string; tenantId: string },
    @Param("userId") userId: string,
  ) {
    return this.usersService.removeMember({
      tenantId: user.tenantId,
      userId,
      actorId: user.id,
    });
  }
}
