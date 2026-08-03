import { Body, Controller, Param, Post, UseGuards } from "@nestjs/common";
import { Public } from "../auth/public.decorator";
import { InternalServiceGuard } from "../common/internal-service.guard";
import { InterviewsService } from "./interviews.service";
import { IngestTranscriptDto } from "./internal-dto";

/**
 * Service-to-service routes for ai-service's voice_agent worker only — never
 * called by a browser/recruiter/candidate client. @Public() bypasses the
 * global JwtAuthGuard (there's no user JWT here); InternalServiceGuard is
 * what actually authenticates the caller — see
 * docs/adr/0006-interview-transcript-storage.md.
 */
@Controller("internal/interview-sessions")
@Public()
@UseGuards(InternalServiceGuard)
export class InternalInterviewsController {
  constructor(private readonly interviews: InterviewsService) {}

  @Post(":id/transcript")
  async ingestTranscript(@Param("id") id: string, @Body() dto: IngestTranscriptDto) {
    return this.interviews.ingestTranscriptAndSummary(id, dto);
  }
}
