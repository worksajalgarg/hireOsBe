import {
  Body,
  Controller,
  Get,
  Param,
  Patch,
  Post,
  Query,
  UploadedFile,
  UseInterceptors,
} from "@nestjs/common";
import { FileInterceptor } from "@nestjs/platform-express";
import { ApiBearerAuth, ApiTags } from "@nestjs/swagger";
import { CurrentUser, RequirePermissions } from "../auth/auth.decorators";
import { PERMISSIONS } from "../common/permissions";
import { JobRolesService } from "./job-roles.service";
import { CreateJobRoleDto, CreateJobRoleFromFileDto, SetJobRoleStatusDto, UpdateJobRoleDto } from "./dto";

const MAX_FILE_BYTES = 10 * 1024 * 1024;

/** Minimal shape of a multer in-memory file — defined locally rather than
 * relying on the ambient `Express.Multer.File` global (environment-specific
 * @types resolution quirks made that global unreliable to depend on here). */
interface UploadedMulterFile {
  buffer: Buffer;
  originalname: string;
  mimetype: string;
  size: number;
}

@ApiTags("job-roles")
@Controller("job-roles")
export class JobRolesController {
  constructor(private readonly jobRoles: JobRolesService) {}

  @Get()
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.JOBS_READ)
  async list(
    @CurrentUser() user: { tenantId: string },
    @Query("status") status?: string,
    @Query("q") q?: string,
  ) {
    return this.jobRoles.findAll(user.tenantId, { status, q });
  }

  @Get(":id")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.JOBS_READ)
  async findOne(@CurrentUser() user: { tenantId: string }, @Param("id") id: string) {
    return this.jobRoles.findOne(user.tenantId, id);
  }

  @Post()
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.JOBS_WRITE)
  async create(@CurrentUser() user: { id: string; tenantId: string }, @Body() dto: CreateJobRoleDto) {
    return this.jobRoles.createFromText({
      tenantId: user.tenantId,
      actorId: user.id,
      title: dto.title,
      jdText: dto.jdText,
      department: dto.department,
      location: dto.location,
      employmentType: dto.employmentType,
      seniority: dto.seniority,
    });
  }

  @Post("upload")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.JOBS_WRITE)
  @UseInterceptors(FileInterceptor("file", { limits: { fileSize: MAX_FILE_BYTES } }))
  async createFromFile(
    @CurrentUser() user: { id: string; tenantId: string },
    @Body() dto: CreateJobRoleFromFileDto,
    @UploadedFile() file: UploadedMulterFile,
  ) {
    return this.jobRoles.createFromFile({
      tenantId: user.tenantId,
      actorId: user.id,
      title: dto.title,
      department: dto.department,
      location: dto.location,
      employmentType: dto.employmentType,
      seniority: dto.seniority,
      file: {
        buffer: file.buffer,
        originalname: file.originalname,
        mimetype: file.mimetype,
        size: file.size,
      },
    });
  }

  @Patch(":id")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.JOBS_WRITE)
  async update(
    @CurrentUser() user: { id: string; tenantId: string },
    @Param("id") id: string,
    @Body() dto: UpdateJobRoleDto,
  ) {
    return this.jobRoles.update(user.tenantId, user.id, id, dto as Record<string, unknown>);
  }

  @Post(":id/status")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.JOBS_WRITE)
  async setStatus(
    @CurrentUser() user: { id: string; tenantId: string },
    @Param("id") id: string,
    @Body() dto: SetJobRoleStatusDto,
  ) {
    return this.jobRoles.setStatus(user.tenantId, user.id, id, dto.status);
  }

  @Post(":id/reparse")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.JOBS_WRITE)
  async reparse(@CurrentUser() user: { id: string; tenantId: string }, @Param("id") id: string) {
    return this.jobRoles.reparse(user.tenantId, user.id, id);
  }

  @Get(":id/jd-download")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.JOBS_READ)
  async jdDownload(@CurrentUser() user: { tenantId: string }, @Param("id") id: string) {
    return this.jobRoles.getJdDownloadUrl(user.tenantId, id);
  }
}
