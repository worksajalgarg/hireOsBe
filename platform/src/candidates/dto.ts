import { IsIn, IsOptional, IsString, MinLength } from "class-validator";

export const APPLICATION_STAGES = [
  "APPLIED",
  "SCREENING",
  "SHORTLISTED",
  "INTERVIEW_SCHEDULED",
  "INTERVIEWED",
  "OFFER",
] as const;
export type ApplicationStageInput = (typeof APPLICATION_STAGES)[number];

export const APPLICATION_STATUSES = ["ACTIVE", "HIRED", "REJECTED", "WITHDRAWN"] as const;
export type ApplicationStatusInput = (typeof APPLICATION_STATUSES)[number];

export class UpdateCandidateDto {
  @IsOptional()
  @IsString()
  fullName?: string;

  @IsOptional()
  @IsString()
  currentTitle?: string;

  @IsOptional()
  @IsString()
  location?: string;
}

export class CreateApplicationDto {
  @IsString()
  @MinLength(1)
  candidateId!: string;

  @IsString()
  @MinLength(1)
  jobRoleId!: string;
}

export class MoveApplicationStageDto {
  @IsIn(APPLICATION_STAGES)
  toStage!: ApplicationStageInput;

  @IsOptional()
  @IsString()
  note?: string;
}

export class SetApplicationDispositionDto {
  @IsIn(APPLICATION_STATUSES)
  status!: ApplicationStatusInput;

  @IsOptional()
  @IsString()
  reason?: string;
}
