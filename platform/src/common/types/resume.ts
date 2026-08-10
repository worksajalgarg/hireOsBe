/** Hand-maintained duplicate of hireOsFe's lib/types/resume.ts. Keep in sync
 * by hand — no automated sync exists between the two repos. */

import type { ExtractionStatus, SourceGrounded } from "./job-role";

export type ResumeStatus = "UPLOADED" | "PARSING" | "PARSED" | "PARSE_FAILED" | "QUARANTINED";

export interface EvidencedClaim extends SourceGrounded {
  claim: string;
}

export interface SkillClaim extends SourceGrounded {
  skill: string;
  yearsExperience?: number | null;
}

export interface WorkHistoryEntry {
  company: string;
  title: string;
  startDate: string | null;
  endDate: string | null;
  isCurrent: boolean | null;
  responsibilities: EvidencedClaim[];
  sourceText: string;
}

export interface UnparsedSection {
  sectionTitle: string;
  rawText: string;
}

/** Mirrors ai-service/app/agents/resume_intelligence_schema.py's
 * ResumeExtractionLLMOutput, camelCased at the ai-service.client.ts boundary. */
export interface ResumeExtractionPayload {
  candidateName?: string | null;
  location?: string | null;
  contact: Record<string, string | null>;
  professionalSummary?: string | null;
  workHistory: WorkHistoryEntry[];
  skills: SkillClaim[];
  education: EvidencedClaim[];
  certifications: EvidencedClaim[];
  projects: EvidencedClaim[];
  awards: EvidencedClaim[];
  publications: EvidencedClaim[];
  languages: EvidencedClaim[];
  verificationTopics: string[];
  unparsedSections: UnparsedSection[];
}

export interface ResumeExtraction {
  id: string;
  tenantId: string;
  resumeId: string;
  attempt: number;
  status: ExtractionStatus;
  extractionJson: ResumeExtractionPayload | null;
  modelVersion: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  startedAt: string | null;
  completedAt: string | null;
  createdAt: string;
}

export interface Resume {
  id: string;
  tenantId: string;
  candidateId: string | null;
  uploadedBy: string;
  originalFilename: string;
  mimeType: string;
  sizeBytes: number;
  status: ResumeStatus;
  extractedTextLength: number | null;
  activeExtraction: ResumeExtraction | null;
  createdAt: string;
  updatedAt: string;
}
