import { IsOptional, IsString, MinLength } from "class-validator";

export class CreateInterviewSessionDto {
  @IsString()
  @MinLength(1)
  candidateRef!: string;

  /** Freeform (e.g. JSON-stringified) resume content, passed through to the
   * voice agent via room metadata so it can ask grounded questions instead
   * of generic ones — see ai-service/app/voice_agent/prompts.py. Treated as
   * untrusted reference data there, not instructions. */
  @IsOptional()
  @IsString()
  resumeContext?: string;
}

export class JoinInterviewDto {
  @IsString()
  @MinLength(1)
  inviteToken!: string;
}
