import { Controller, Get } from "@nestjs/common";

@Controller("role-contexts")
export class RoleContextController {
  @Get("_stub")
  stub() {
    return { module: "role-context", status: "not implemented — Sprint 2" };
  }
}
