import { Module } from "@nestjs/common";
import { CandidatesController } from "./candidates.controller";

/**
 * Stub module reserving the boundary for Candidate Intelligence (PRD Section
 * 5.3 / FR-301..FR-306). Implementation lands in Sprint 3 (Resume evidence
 * prototype).
 */
@Module({
  controllers: [CandidatesController],
})
export class CandidatesModule {}
