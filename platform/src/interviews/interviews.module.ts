import { Module } from "@nestjs/common";
import { InterviewsController } from "./interviews.controller";
import { InternalInterviewsController } from "./internal-interviews.controller";
import { InterviewsService } from "./interviews.service";
import { InterviewRetentionService } from "./interview-retention.service";
import { LiveKitService } from "./livekit.service";
import { AuditModule } from "../audit/audit.module";

/**
 * LiveKit-backed AI voice interview sessions (PRD Section 7.1 — Voice
 * Interviewer boundary). Owns token minting, room lifecycle, and Egress
 * recording; conducts-the-interview logic lives in ai-service's voice_agent
 * worker, dispatched by livekit-server directly (never calls back here) —
 * except for InternalInterviewsController's transcript-ingest endpoint,
 * a deliberate, scoped, post-call exception (see
 * docs/adr/0006-interview-transcript-storage.md).
 */
@Module({
  imports: [AuditModule],
  controllers: [InterviewsController, InternalInterviewsController],
  providers: [InterviewsService, LiveKitService, InterviewRetentionService],
})
export class InterviewsModule {}
