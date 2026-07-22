import { Body, Controller, Get, Post } from "@nestjs/common";
import { TenantContextService } from "../common/tenant-context.service";
import { TenantService } from "./tenant.service";

interface CreateTenantDto {
  name: string;
  domain: string;
}

@Controller("tenants")
export class TenantController {
  constructor(
    private readonly tenantService: TenantService,
    private readonly tenantContext: TenantContextService,
  ) {}

  /**
   * Bootstraps a new tenant. In production this sits behind a platform-admin
   * onboarding flow, not an open endpoint — left unguarded here only because
   * no tenant/actor exists yet to authenticate the very first call.
   */
  @Post()
  async create(@Body() dto: CreateTenantDto) {
    return this.tenantService.create({
      name: dto.name,
      domain: dto.domain,
      actorId: this.tenantContext.getActorId(),
    });
  }

  @Get("me")
  async getCurrent() {
    return this.tenantService.findById(this.tenantContext.getTenantId());
  }
}
