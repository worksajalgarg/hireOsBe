import { Controller, Get } from "@nestjs/common";
import { Public } from "../auth/public.decorator";

@Controller("candidates")
export class CandidatesController {
  @Public()
  @Get("_stub")
  stub() {
    return { module: "candidates", status: "not implemented — Sprint 3" };
  }
}
