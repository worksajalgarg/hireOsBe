import { Controller, Get } from "@nestjs/common";
import { Public } from "../auth/public.decorator";

@Controller("workflow")
export class WorkflowController {
  @Public()
  @Get("_stub")
  stub() {
    return { module: "workflow", status: "not implemented — Sprints 4-8" };
  }
}
