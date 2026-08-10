import {
  BadRequestException,
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Patch,
  Post,
  Req,
  Res,
  UploadedFile,
  UseInterceptors,
} from "@nestjs/common";
import { FileInterceptor } from "@nestjs/platform-express";
import { ApiBearerAuth, ApiBody, ApiConsumes, ApiTags } from "@nestjs/swagger";
import type { Request, Response } from "express";
import { CurrentUser, RequirePermissions } from "../auth/auth.decorators";
import { Roles } from "../common/roles.decorator";
import { UserRole } from "../common/types";
import { PERMISSIONS } from "../common/permissions";
import { UpdateResumeWorkingJsonDto } from "./dto";
import { ResumesService } from "./resumes.service";

type AuthUser = { id: string; tenantId: string };

type UploadedResumeFile = {
  originalname: string;
  mimetype: string;
  buffer: Buffer;
  size: number;
};

const uploadLimitMb = Number(process.env.RESUME_MAX_UPLOAD_MB ?? "10");
const uploadLimitBytes =
  (Number.isFinite(uploadLimitMb) && uploadLimitMb > 0 ? uploadLimitMb : 10) *
  1024 *
  1024;

@ApiTags("resumes")
@ApiBearerAuth()
@Controller("resumes")
@Roles(UserRole.Admin)
export class ResumesController {
  constructor(private readonly resumesService: ResumesService) {}

  @Post()
  @RequirePermissions(PERMISSIONS.RESUMES_WRITE)
  @ApiConsumes("multipart/form-data")
  @ApiBody({
    schema: {
      type: "object",
      properties: { file: { type: "string", format: "binary" } },
      required: ["file"],
    },
  })
  @UseInterceptors(FileInterceptor("file", { limits: { fileSize: uploadLimitBytes } }))
  async upload(
    @CurrentUser() user: AuthUser,
    @UploadedFile() file: UploadedResumeFile | undefined,
  ) {
    if (!file?.buffer?.length) {
      throw new BadRequestException("file is required");
    }
    return this.resumesService.upload({
      tenantId: user.tenantId,
      userId: user.id,
      filename: file.originalname,
      contentType: file.mimetype,
      buffer: file.buffer,
    });
  }

  @Get()
  @RequirePermissions(PERMISSIONS.RESUMES_READ)
  async list(@CurrentUser() user: AuthUser) {
    return this.resumesService.list(user.tenantId);
  }

  @Get(":id")
  @RequirePermissions(PERMISSIONS.RESUMES_READ)
  async get(@CurrentUser() user: AuthUser, @Param("id") id: string) {
    return this.resumesService.get(user.tenantId, id);
  }

  @Patch(":id")
  @RequirePermissions(PERMISSIONS.RESUMES_WRITE)
  async updateWorkingJson(
    @CurrentUser() user: AuthUser,
    @Param("id") id: string,
    @Body() dto: UpdateResumeWorkingJsonDto,
  ) {
    return this.resumesService.updateWorkingJson(user.tenantId, id, dto.workingJson);
  }

  @Delete(":id")
  @RequirePermissions(PERMISSIONS.RESUMES_WRITE)
  async remove(@CurrentUser() user: AuthUser, @Param("id") id: string) {
    return this.resumesService.delete(user.tenantId, id);
  }

  @Post(":id/extract")
  @RequirePermissions(PERMISSIONS.RESUMES_EXTRACT)
  async extract(
    @CurrentUser() user: AuthUser,
    @Param("id") id: string,
    @Req() req: Request,
    @Res() res: Response,
  ) {
    const { resume, buffer } = await this.resumesService.getFileBuffer(
      user.tenantId,
      id,
    );

    const aiBase = (process.env.AI_SERVICE_URL ?? "http://localhost:8000").replace(
      /\/$/,
      "",
    );

    const form = new FormData();
    const blob = new Blob([new Uint8Array(buffer)], { type: resume.contentType });
    form.append("file", blob, resume.originalFilename);

    const abort = new AbortController();
    res.on("close", () => {
      if (!res.writableEnded) abort.abort();
    });

    let upstream: globalThis.Response;
    try {
      const internalToken = process.env.AI_SERVICE_TOKEN;
      upstream = await fetch(`${aiBase}/resume-extractor/extract`, {
        method: "POST",
        body: form,
        signal: abort.signal,
        headers: internalToken ? { "x-ai-service-token": internalToken } : undefined,
      });
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        await this.resumesService.persistExtractionFailure(
          user.tenantId,
          id,
          "Extraction cancelled before the AI service responded",
        );
        res.end();
        return;
      }
      await this.resumesService.persistExtractionFailure(
        user.tenantId,
        id,
        `AI service unreachable: ${(err as Error).message}`,
      );
      res.status(502).json({
        message: `AI service unreachable: ${(err as Error).message}`,
      });
      return;
    }

    if (!upstream.ok || !upstream.body) {
      const text = await upstream.text().catch(() => "");
      await this.resumesService.persistExtractionFailure(
        user.tenantId,
        id,
        text || `AI service error ${upstream.status}`,
      );
      res.status(502).json({
        message: text || `AI service error ${upstream.status}`,
      });
      return;
    }

    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no");
    if (typeof res.flushHeaders === "function") {
      res.flushHeaders();
    }

    const reader = upstream.body.getReader();
    const decoder = new TextDecoder();
    let bufferText = "";
    let parseSource: string | null = null;
    let finalResume: Record<string, unknown> | null = null;
    let failedMessage: string | null = null;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        bufferText += chunk;
        res.write(chunk);

        const parts = bufferText.split("\n\n");
        bufferText = parts.pop() ?? "";
        for (const part of parts) {
          // Join every data: line in the frame (SSE allows multi-line payloads).
          // Using only the first line dropped oversized final_json events and left
          // working_json null even though the FE timeline showed Final JSON.
          const dataPayload = part
            .split("\n")
            .filter((l) => l.startsWith("data:"))
            .map((l) => l.slice(5).trimStart())
            .join("\n");
          if (!dataPayload) continue;
          try {
            const event = JSON.parse(dataPayload) as {
              stage?: string;
              status?: string;
              message?: string;
              data?: Record<string, unknown>;
            };
            if (
              (event.stage === "docling" || event.stage === "ocr_fallback") &&
              event.status === "success" &&
              typeof event.data?.source === "string"
            ) {
              parseSource = event.data.source;
            }
            if (event.stage === "final_json" && event.status === "success") {
              const resumeJson = event.data?.resume;
              if (resumeJson && typeof resumeJson === "object" && !Array.isArray(resumeJson)) {
                finalResume = resumeJson as Record<string, unknown>;
              }
            }
            if (event.stage === "error" && event.status === "failed") {
              failedMessage = event.message ?? "Extraction failed";
            }
          } catch {
            // ignore parse errors on partial frames
          }
        }
      }

      if (finalResume) {
        await this.resumesService.persistExtractionSuccess(user.tenantId, id, {
          resumeJson: finalResume,
          parseSource,
        });
      } else if (failedMessage) {
        await this.resumesService.persistExtractionFailure(
          user.tenantId,
          id,
          failedMessage,
        );
      } else {
        await this.resumesService.persistExtractionFailure(
          user.tenantId,
          id,
          "Extraction stream ended without final JSON",
        );
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        await this.resumesService.persistExtractionFailure(
          user.tenantId,
          id,
          "Extraction cancelled by the client",
        );
      } else {
        await this.resumesService.persistExtractionFailure(
          user.tenantId,
          id,
          (err as Error).message,
        );
        if (!res.writableEnded) {
          res.write(
            `data: ${JSON.stringify({
              stage: "error",
              status: "failed",
              message: (err as Error).message,
              data: {},
            })}\n\n`,
          );
        }
      }
    } finally {
      if (!res.writableEnded) {
        res.end();
      }
    }
  }
}
