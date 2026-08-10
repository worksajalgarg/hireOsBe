import { Module } from "@nestjs/common";
import { CandidatesController } from "./candidates.controller";
import { CandidatesService } from "./candidates.service";
import { ApplicationsController } from "./applications.controller";
import { ApplicationsService } from "./applications.service";
import { AuditModule } from "../audit/audit.module";

/**
 * Candidate Intelligence (PRD Section 5.3 / FR-301..FR-306) — now implemented:
 * candidate read/update and the Application (candidate<->job-role pipeline
 * entry) lifecycle. Candidates themselves are created by
 * resumes/candidate-linking.service.ts, not here.
 */
@Module({
  imports: [AuditModule],
  controllers: [CandidatesController, ApplicationsController],
  providers: [CandidatesService, ApplicationsService],
  exports: [CandidatesService, ApplicationsService],
})
export class CandidatesModule {}
