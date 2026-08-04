import { Controller, Get } from "@nestjs/common";
import { Public } from "../auth/public.decorator";

@Controller("integrations")
export class IntegrationsController {
  @Public()
  @Get("_stub")
  stub() {
    return { module: "integrations", status: "not implemented — Sprint 9" };
  }
}
