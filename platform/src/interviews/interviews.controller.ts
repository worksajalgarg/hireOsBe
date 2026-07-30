import { Body, Controller, Param, Post } from "@nestjs/common";
import { ApiBearerAuth, ApiTags } from "@nestjs/swagger";
import { Public } from "../auth/public.decorator";
import { CurrentUser, RequirePermissions } from "../auth/auth.decorators";
import { PERMISSIONS } from "../common/permissions";
import { InterviewsService } from "./interviews.service";
import { CreateInterviewSessionDto, JoinInterviewDto } from "./dto";

@ApiTags("interviews")
@Controller("interviews")
export class InterviewsController {
  constructor(private readonly interviews: InterviewsService) {}

  @Post()
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.INTERVIEWS_MANAGE)
  async create(
    @CurrentUser() user: { id: string; tenantId: string },
    @Body() dto: CreateInterviewSessionDto,
  ) {
    const { id, inviteToken } = await this.interviews.createSession({
      tenantId: user.tenantId,
      actorId: user.id,
      candidateRef: dto.candidateRef,
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
