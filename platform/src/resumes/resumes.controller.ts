import { Controller, Delete, Get, Param, Post, UploadedFile, UseInterceptors } from "@nestjs/common";
import { FileInterceptor } from "@nestjs/platform-express";
import { ApiBearerAuth, ApiTags } from "@nestjs/swagger";
import { CurrentUser, RequirePermissions } from "../auth/auth.decorators";
import { PERMISSIONS } from "../common/permissions";
import { ResumesService } from "./resumes.service";

const MAX_FILE_BYTES = 10 * 1024 * 1024;

interface UploadedMulterFile {
  buffer: Buffer;
  originalname: string;
  mimetype: string;
  size: number;
}

@ApiTags("resumes")
@Controller()
export class ResumesController {
  constructor(private readonly resumes: ResumesService) {}

  // One file per request by design — the backend parses synchronously
  // in-request (see the implementation plan's deployment-reality note on
  // platform still being a Vercel serverless function); a batch endpoint
  // processing N sequential LLM calls in one request would blow past any
  // reasonable function timeout. The frontend fans a multi-file selection
  // out into N bounded-concurrency requests against this endpoint.
  @Post("job-roles/:jobRoleId/resumes")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.RESUMES_UPLOAD)
  @UseInterceptors(FileInterceptor("file", { limits: { fileSize: MAX_FILE_BYTES } }))
  async upload(
    @CurrentUser() user: { id: string; tenantId: string },
    @Param("jobRoleId") jobRoleId: string,
    @UploadedFile() file: UploadedMulterFile,
  ) {
    return this.resumes.upload({
      tenantId: user.tenantId,
      actorId: user.id,
      jobRoleId,
      file: {
        buffer: file.buffer,
        originalname: file.originalname,
        mimetype: file.mimetype,
        size: file.size,
      },
    });
  }

  @Get("job-roles/:jobRoleId/resumes")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.RESUMES_READ)
  async listForJobRole(@CurrentUser() user: { tenantId: string }, @Param("jobRoleId") jobRoleId: string) {
    return this.resumes.listForJobRole(user.tenantId, jobRoleId);
  }

  @Get("resumes/:id")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.RESUMES_READ)
  async findOne(@CurrentUser() user: { tenantId: string }, @Param("id") id: string) {
    return this.resumes.findOne(user.tenantId, id);
  }

  @Get("resumes/:id/download")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.RESUMES_READ)
  async download(@CurrentUser() user: { tenantId: string }, @Param("id") id: string) {
    return this.resumes.getDownloadUrl(user.tenantId, id);
  }

  @Post("resumes/:id/reparse")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.RESUMES_UPLOAD)
  async reparse(@CurrentUser() user: { id: string; tenantId: string }, @Param("id") id: string) {
    return this.resumes.reparse(user.tenantId, user.id, id);
  }

  @Delete("resumes/:id")
  @ApiBearerAuth()
  @RequirePermissions(PERMISSIONS.RESUMES_UPLOAD)
  async remove(@CurrentUser() user: { id: string; tenantId: string }, @Param("id") id: string) {
    return this.resumes.delete(user.tenantId, user.id, id);
  }
}
