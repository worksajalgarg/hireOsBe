import {
  Body,
  Controller,
  Get,
  Param,
  Patch,
  Post,
} from "@nestjs/common";
import { ApiBearerAuth, ApiTags } from "@nestjs/swagger";
import { IsEmail, IsEnum } from "class-validator";
import { UserRole } from "../common/types";
import { Roles } from "../common/roles.decorator";
import { RequirePermissions, CurrentUser } from "../auth/auth.decorators";
import { UsersService } from "./users.service";
import { ChangePasswordDto, UpdateProfileDto } from "../auth/dto";
import { PERMISSIONS } from "../common/permissions";

class InviteUserDto {
  @IsEmail()
  email!: string;

  @IsEnum(UserRole)
  role!: UserRole;
}

class ChangeRoleDto {
  @IsEnum(UserRole)
  role!: UserRole;
}

@ApiTags("users")
@ApiBearerAuth()
@Controller("users")
export class UsersController {
  constructor(private readonly usersService: UsersService) {}

  @Get("me")
  async me(@CurrentUser() user: { id: string; tenantId: string }) {
    return this.usersService.getMe(user.id, user.tenantId);
  }

  @Patch("me/profile")
  @RequirePermissions(PERMISSIONS.PROFILE_WRITE)
  async updateProfile(
    @CurrentUser() user: { id: string },
    @Body() dto: UpdateProfileDto,
  ) {
    return this.usersService.updateProfile(user.id, dto);
  }

  @Post("me/change-password")
  async changePassword(
    @CurrentUser() user: { id: string },
    @Body() dto: ChangePasswordDto,
  ) {
    return this.usersService.changePassword(user.id, dto);
  }

  @Post()
  @Roles(UserRole.Admin)
  @RequirePermissions(PERMISSIONS.MEMBERS_INVITE)
  async invite(
    @CurrentUser() user: { id: string; tenantId: string },
    @Body() dto: InviteUserDto,
  ) {
    return this.usersService.invite({
      tenantId: user.tenantId,
      email: dto.email,
      role: dto.role,
      actorId: user.id,
    });
  }

  @Get()
  @Roles(UserRole.Admin, UserRole.Auditor)
  @RequirePermissions(PERMISSIONS.MEMBERS_READ)
  async list(@CurrentUser() user: { tenantId: string }) {
    return this.usersService.listForTenant(user.tenantId);
  }

  @Patch(":id/role")
  @Roles(UserRole.Admin)
  @RequirePermissions(PERMISSIONS.MEMBERS_ROLE_WRITE)
  async changeRole(
    @CurrentUser() user: { id: string; tenantId: string },
    @Param("id") id: string,
    @Body() dto: ChangeRoleDto,
  ) {
    return this.usersService.changeRole({
      tenantId: user.tenantId,
      userId: id,
      role: dto.role,
      actorId: user.id,
    });
  }
}
