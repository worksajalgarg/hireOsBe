import { IsObject } from "class-validator";

export class UpdateResumeWorkingJsonDto {
  @IsObject()
  workingJson!: Record<string, unknown>;
}
