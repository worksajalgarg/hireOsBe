import { Module } from "@nestjs/common";
import { IntegrationsController } from "./integrations.controller";

/**
 * Stub module reserving the boundary for CSV/API/webhook and single-ATS
 * integrations (PRD Section 3, explicitly limited scope — no native
 * multi-ATS integrations before the first design partner). Lands in
 * Sprint 9 "Enterprise controls".
 */
@Module({
  controllers: [IntegrationsController],
})
export class IntegrationsModule {}
