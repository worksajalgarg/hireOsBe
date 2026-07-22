import { Controller, Get } from "@nestjs/common";

@Controller("workflow")
export class WorkflowController {
  @Get("_stub")
  stub() {
    return { module: "workflow", status: "not implemented — Sprints 4-8" };
  }
}
