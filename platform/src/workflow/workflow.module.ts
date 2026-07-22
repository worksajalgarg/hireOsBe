import { Module } from "@nestjs/common";
import { WorkflowController } from "./workflow.controller";

/**
 * Stub module reserving the boundary for the recruiter/candidate workflow
 * state machine (PRD Section 4 / Section 5.7 Decision Workspace).
 * Implementation lands progressively across Sprints 4-8.
 */
@Module({
  controllers: [WorkflowController],
})
export class WorkflowModule {}
