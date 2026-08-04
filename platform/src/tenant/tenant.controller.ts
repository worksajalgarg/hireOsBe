import { Body, Controller, Get, Post } from "@nestjs/common";
import { ApiBearerAuth, ApiTags } from "@nestjs/swagger";
import { IsString, MinLength } from "class-validator";
import { TenantContextService } from "../common/tenant-context.service";
import { TenantService } from "./tenant.service";
import { Public } from "../auth/public.decorator";
import { CurrentUser } from "../auth/auth.decorators";

class CreateTenantDto {
  @IsString()
  @MinLength(1)
  name!: string;

  @IsString()
  @MinLength(1)
  domain!: string;
}

@ApiTags("tenants")
@Controller("tenants")
export class TenantController {
  constructor(
    private readonly tenantService: TenantService,
    private readonly tenantContext: TenantContextService,
  ) {}

  /**
   * Bootstraps a new tenant. Public only for local bootstrap; production
   * should gate this behind platform-admin onboarding.
   */
  @Public()
  @Post()
  async create(@Body() dto: CreateTenantDto) {
    let actorId = "system-bootstrap";
    try {
      actorId = this.tenantContext.getActorId();
    } catch {
      // bootstrap without auth
    }
    return this.tenantService.create({
      name: dto.name,
      domain: dto.domain,
      actorId,
    });
  }

  @ApiBearerAuth()
  @Get("me")
  async getCurrent(@CurrentUser() user: { tenantId: string }) {
    return this.tenantService.findById(user.tenantId);
  }
}
