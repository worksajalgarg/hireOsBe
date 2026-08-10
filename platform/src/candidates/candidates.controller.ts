import { Body, Controller, Get, Param, Patch, Query } from "@nestjs/common";
import { ApiBearerAuth, ApiTags } from "@nestjs/swagger";
import { CurrentUser, RequirePermissions } from "../auth/auth.decorators";
import { PERMISSIONS } from "../common/permissions";
import { CandidatesService } from "./candidates.service";
import { UpdateCandidateDto } from "./dto";

@ApiTags("candidates")
@Controller("candidates")
export class CandidatesController {
  constructor(private readonly candidates: CandidatesService) {}

  @Get()
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.CANDIDATES_READ)
  async list(@CurrentUser() user: { tenantId: string }, @Query("q") q?: string) {
    return this.candidates.findAll(user.tenantId, q);
  }

  @Get(":id")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.CANDIDATES_READ)
  async findOne(@CurrentUser() user: { tenantId: string }, @Param("id") id: string) {
    return this.candidates.findOne(user.tenantId, id);
  }

  @Patch(":id")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.CANDIDATES_WRITE)
  async update(
    @CurrentUser() user: { id: string; tenantId: string },
    @Param("id") id: string,
    @Body() dto: UpdateCandidateDto,
  ) {
    return this.candidates.update(user.tenantId, user.id, id, dto as Record<string, unknown>);
  }
}
