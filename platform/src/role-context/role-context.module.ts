import { Module } from "@nestjs/common";
import { RoleContextController } from "./role-context.controller";

/**
 * Stub module reserving the boundary for Role Context Studio (PRD Section
 * 5.2 / FR-201..FR-206). Implementation lands in Sprint 2 (Role Context
 * prototype) — this module must call services/ai-service's Role Intelligence
 * agent for rubric generation, never an LLM provider directly.
 */
@Module({
  controllers: [RoleContextController],
})
export class RoleContextModule {}
