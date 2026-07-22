import { Controller, Get } from "@nestjs/common";

@Controller("integrations")
export class IntegrationsController {
  @Get("_stub")
  stub() {
    return { module: "integrations", status: "not implemented — Sprint 9" };
  }
}
