import { IsIn, IsOptional, IsString, MinLength } from "class-validator";

export const JOB_ROLE_STATUSES = ["DRAFT", "OPEN", "ON_HOLD", "CLOSED"] as const;
export type JobRoleStatusInput = (typeof JOB_ROLE_STATUSES)[number];

export class CreateJobRoleDto {
  @IsString()
  @MinLength(1)
  title!: string;

  @IsString()
  @MinLength(1)
  jdText!: string;

  @IsOptional()
  @IsString()
  department?: string;

  @IsOptional()
  @IsString()
  location?: string;

  @IsOptional()
  @IsString()
  employmentType?: string;

  @IsOptional()
  @IsString()
  seniority?: string;
}

export class CreateJobRoleFromFileDto {
  @IsString()
  @MinLength(1)
  title!: string;

  @IsOptional()
  @IsString()
  department?: string;

  @IsOptional()
  @IsString()
  location?: string;

  @IsOptional()
  @IsString()
  employmentType?: string;

  @IsOptional()
  @IsString()
  seniority?: string;
}

export class UpdateJobRoleDto {
  @IsOptional()
  @IsString()
  title?: string;

  @IsOptional()
  @IsString()
  department?: string;

  @IsOptional()
  @IsString()
  location?: string;

  @IsOptional()
  @IsString()
  employmentType?: string;

  @IsOptional()
  @IsString()
  seniority?: string;
}

export class SetJobRoleStatusDto {
  @IsIn(JOB_ROLE_STATUSES)
  status!: JobRoleStatusInput;
}
