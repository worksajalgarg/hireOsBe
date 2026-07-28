import { IsEmail, IsOptional, IsString, MinLength } from "class-validator";

export class LoginDto {
  @IsEmail()
  email!: string;

  @IsString()
  @MinLength(8)
  password!: string;

  @IsOptional()
  @IsString()
  tenantId?: string;
}

export class ForgotPasswordDto {
  @IsEmail()
  email!: string;
}

export class ResetPasswordDto {
  @IsString()
  token!: string;

  @IsString()
  @MinLength(8)
  password!: string;
}

export class SsoCallbackDto {
  @IsString()
  provider!: string;

  @IsString()
  code!: string;

  @IsOptional()
  @IsString()
  tenantId?: string;
}

export class MfaVerifyDto {
  @IsString()
  code!: string;
}

export class ChangePasswordDto {
  @IsString()
  @MinLength(8)
  currentPassword!: string;

  @IsString()
  @MinLength(8)
  newPassword!: string;
}

export class UpdateProfileDto {
  @IsOptional()
  @IsString()
  firstName?: string;

  @IsOptional()
  @IsString()
  lastName?: string;

  @IsOptional()
  @IsString()
  phone?: string;

  @IsOptional()
  @IsString()
  jobTitle?: string;

  @IsOptional()
  @IsString()
  avatarUrl?: string;

  @IsOptional()
  preferencesJson?: Record<string, unknown>;
}

export class InviteMemberDto {
  @IsEmail()
  email!: string;

  @IsString()
  roleId!: string;
}

export class UpdateMemberRoleDto {
  @IsString()
  roleId!: string;
}

export class UpdateWorkspaceSettingsDto {
  @IsOptional()
  @IsString()
  name?: string;

  @IsOptional()
  @IsString()
  domain?: string;

  @IsOptional()
  @IsString()
  logoUrl?: string;

  @IsOptional()
  settingsJson?: Record<string, unknown>;

  @IsOptional()
  retentionDays?: number;

  @IsOptional()
  audioStorageEnabled?: boolean;

  @IsOptional()
  humanOverrideRequired?: boolean;
}

export class CreateRoleDto {
  @IsString()
  name!: string;

  @IsOptional()
  @IsString()
  description?: string;

  @IsOptional()
  permissionSlugs?: string[];
}

export class AcceptInviteDto {
  @IsString()
  token!: string;

  @IsString()
  @MinLength(8)
  password!: string;

  @IsOptional()
  @IsString()
  firstName?: string;

  @IsOptional()
  @IsString()
  lastName?: string;
}
