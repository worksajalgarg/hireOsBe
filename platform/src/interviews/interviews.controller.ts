import { Body, Controller, Param, Post, UseGuards } from "@nestjs/common";
import { ApiBearerAuth, ApiTags } from "@nestjs/swagger";
import { Throttle } from "@nestjs/throttler";
import { Public } from "../auth/public.decorator";
import { CurrentUser, RequirePermissions } from "../auth/auth.decorators";
import { PERMISSIONS } from "../common/permissions";
import { TenantThrottlerGuard } from "../common/tenant-throttler.guard";
import { InterviewsService } from "./interviews.service";
import { CreateInterviewSessionDto, JoinInterviewDto } from "./dto";

@ApiTags("interviews")
@Controller("interviews")
export class InterviewsController {
  constructor(private readonly interviews: InterviewsService) {}

  // Stricter than the app-wide generic 100/min-per-IP throttle
  // (app.module.ts) — tenant-scoped, since each call here creates a real
  // LiveKit room + dispatches a worker job with real STT/LLM/TTS cost
  // regardless of caller IP. See docs/adr/0006-interview-transcript-storage.md.
  @Post()
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.INTERVIEWS_MANAGE)
  @UseGuards(TenantThrottlerGuard)
  @Throttle({ default: { limit: 20, ttl: 60_000 } })
  async create(
    @CurrentUser() user: { id: string; tenantId: string },
    @Body() dto: CreateInterviewSessionDto,
  ) {
    const { id, inviteToken } = await this.interviews.createSession({
      tenantId: user.tenantId,
      actorId: user.id,
      candidateRef: dto.candidateRef,
      resumeContext: dto.resumeContext,
      sessionType: dto.sessionType,
      promptId: dto.promptId,
    });
    const appUrl = process.env.CANDIDATE_APP_URL ?? process.env.CORS_ORIGIN ?? "http://localhost:3000";
    return { id, inviteUrl: `${appUrl}/candidate/interview/${inviteToken}` };
  }

  @Post("join")
  @Public()
  async join(@Body() dto: JoinInterviewDto) {
    return this.interviews.joinSession(dto.inviteToken);
  }

  @Post(":id/token")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.INTERVIEWS_MANAGE)
  async recruiterToken(
    @CurrentUser() user: { id: string; tenantId: string },
    @Param("id") id: string,
  ) {
    return this.interviews.mintRecruiterToken({ tenantId: user.tenantId, actorId: user.id, sessionId: id });
  }

  @Post(":id/end")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.INTERVIEWS_MANAGE)
  async end(@CurrentUser() user: { id: string; tenantId: string }, @Param("id") id: string) {
    return this.interviews.endSession({ tenantId: user.tenantId, actorId: user.id, sessionId: id });
  }
}
