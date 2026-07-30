import { Module } from "@nestjs/common";
import { InterviewsController } from "./interviews.controller";
import { InterviewsService } from "./interviews.service";
import { LiveKitService } from "./livekit.service";
import { AuditModule } from "../audit/audit.module";

/**
 * LiveKit-backed AI voice interview sessions (PRD Section 7.1 — Voice
 * Interviewer boundary). Owns token minting, room lifecycle, and Egress
 * recording; conducts-the-interview logic lives in ai-service's voice_agent
 * worker, dispatched by livekit-server directly (never calls back here).
 */
@Module({
  imports: [AuditModule],
  controllers: [InterviewsController],
  providers: [InterviewsService, LiveKitService],
})
export class InterviewsModule {}
