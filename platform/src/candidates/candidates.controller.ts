import { Controller, Get } from "@nestjs/common";

@Controller("candidates")
export class CandidatesController {
  @Get("_stub")
  stub() {
    return { module: "candidates", status: "not implemented — Sprint 3" };
  }
}
