/** Hand-maintained duplicate of hireOsFe's lib/types/candidate.ts. */

export type CandidateSource = "RESUME_UPLOAD" | "MANUAL" | "REFERRAL" | "IMPORT";

export interface Candidate {
  id: string;
  tenantId: string;
  fullName: string;
  primaryEmail: string | null;
  primaryPhone: string | null;
  currentTitle: string | null;
  location: string | null;
  source: CandidateSource;
  createdAt: string;
  updatedAt: string;
}
