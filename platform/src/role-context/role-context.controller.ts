import { Controller, Get } from "@nestjs/common";
import { Public } from "../auth/public.decorator";

@Controller("role-contexts")
export class RoleContextController {
  @Public()
  @Get("_stub")
  stub() {
    return { module: "role-context", status: "not implemented — Sprint 2" };
  }
}
