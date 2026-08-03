import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Patch,
  Post,
  UseGuards,
} from "@nestjs/common";
import { PromptsService } from "./prompts.service";
import { CreatePromptTemplateDto, UpdatePromptTemplateDto } from "./dto";
import { JwtAuthGuard } from "../auth/jwt-auth.guard";
import { TenantAccessGuard } from "../auth/tenant-access.guard";
import { PermissionsGuard } from "../auth/permissions.guard";
import { CurrentUser } from "../auth/auth.decorators";

@Controller("prompts")
@UseGuards(JwtAuthGuard, TenantAccessGuard, PermissionsGuard)
export class PromptsController {
  constructor(private readonly promptsService: PromptsService) {}

  @Get()
  async list(@CurrentUser() user: { tenantId: string }) {
    return this.promptsService.listForTenant(user.tenantId);
  }

  @Get(":id")
  async getOne(
    @CurrentUser() user: { tenantId: string },
    @Param("id") id: string,
  ) {
    return this.promptsService.getById(user.tenantId, id);
  }

  @Post()
  async create(
    @CurrentUser() user: { tenantId: string; userId: string },
    @Body() dto: CreatePromptTemplateDto,
  ) {
    return this.promptsService.create(user.tenantId, user.userId, dto);
  }

  @Patch(":id")
  async update(
    @CurrentUser() user: { tenantId: string; userId: string },
    @Param("id") id: string,
    @Body() dto: UpdatePromptTemplateDto,
  ) {
    return this.promptsService.update(user.tenantId, user.userId, id, dto);
  }

  @Delete(":id")
  async delete(
    @CurrentUser() user: { tenantId: string; userId: string },
    @Param("id") id: string,
  ) {
    return this.promptsService.delete(user.tenantId, user.userId, id);
  }
}
