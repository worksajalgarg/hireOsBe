import { Body, Controller, Get, Param, Patch, Post } from "@nestjs/common";
import { ApiBearerAuth, ApiTags } from "@nestjs/swagger";
import { CurrentUser, RequirePermissions } from "../auth/auth.decorators";
import { PERMISSIONS } from "../common/permissions";
import { ApplicationsService } from "./applications.service";
import { CreateApplicationDto, MoveApplicationStageDto, SetApplicationDispositionDto } from "./dto";

@ApiTags("applications")
@Controller()
export class ApplicationsController {
  constructor(private readonly applications: ApplicationsService) {}

  @Get("job-roles/:jobRoleId/pipeline")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.CANDIDATES_READ)
  async pipeline(@CurrentUser() user: { tenantId: string }, @Param("jobRoleId") jobRoleId: string) {
    return this.applications.listPipeline(user.tenantId, jobRoleId);
  }

  @Post("applications")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.CANDIDATES_WRITE)
  async create(@CurrentUser() user: { id: string; tenantId: string }, @Body() dto: CreateApplicationDto) {
    return this.applications.create(user.tenantId, user.id, dto);
  }

  @Patch("applications/:id/stage")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.CANDIDATES_WRITE)
  async moveStage(
    @CurrentUser() user: { id: string; tenantId: string },
    @Param("id") id: string,
    @Body() dto: MoveApplicationStageDto,
  ) {
    return this.applications.moveStage(user.tenantId, user.id, id, dto);
  }

  @Patch("applications/:id/disposition")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.CANDIDATES_WRITE)
  async setDisposition(
    @CurrentUser() user: { id: string; tenantId: string },
    @Param("id") id: string,
    @Body() dto: SetApplicationDispositionDto,
  ) {
    return this.applications.setDisposition(user.tenantId, user.id, id, dto);
  }
}
