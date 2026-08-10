import { IsIn, IsOptional, IsString, MinLength } from "class-validator";

export const SESSION_TYPES = ["candidate_interview", "hiring_manager_discovery"] as const;
export type SessionType = (typeof SESSION_TYPES)[number];

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

  /** Which voice-agent persona conducts this session — see
   * ai-service/app/voice_agent/worker.py's sessionType branch. Defaults to
   * "candidate_interview" (worker.py's own default) when omitted, so
   * existing callers that don't send this are unaffected. */
  @IsOptional()
  @IsIn(SESSION_TYPES)
  sessionType?: SessionType;

  @IsOptional()
  @IsString()
  promptId?: string;
}

export class JoinInterviewDto {
  @IsString()
  @MinLength(1)
  inviteToken!: string;
}
