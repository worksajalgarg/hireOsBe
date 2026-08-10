import { Module } from "@nestjs/common";
import { ResumesController } from "./resumes.controller";
import { ResumesService } from "./resumes.service";
import { CandidateLinkingService } from "./candidate-linking.service";
import { AuditModule } from "../audit/audit.module";

/**
 * Resume upload -> ai-service parse -> Candidate/Application linking.
 * Replaces the former candidates/ stub's file-handling scope; CandidatesModule
 * owns the read/pipeline side once a Candidate exists.
 */
@Module({
  imports: [AuditModule],
  controllers: [ResumesController],
  providers: [ResumesService, CandidateLinkingService],
  exports: [ResumesService, CandidateLinkingService],
})
export class ResumesModule {}
