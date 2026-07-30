import { IsString, MinLength } from "class-validator";

export class CreateInterviewSessionDto {
  @IsString()
  @MinLength(1)
  candidateRef!: string;
}

export class JoinInterviewDto {
  @IsString()
  @MinLength(1)
  inviteToken!: string;
}
