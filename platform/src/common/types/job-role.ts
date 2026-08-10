/** Hand-maintained duplicate of hireOsFe's lib/types/job-role.ts. Keep in sync
 * by hand — no automated sync exists between the two repos. */

export type JobRoleStatus = "DRAFT" | "OPEN" | "ON_HOLD" | "CLOSED";
export type JdSourceType = "UPLOAD" | "PASTE";
export type ExtractionStatus = "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED";

/** Mirrors ai-service's SourceGrounded — no claim exists without a pointer
 * back to the source text it was extracted from. */
export interface SourceGrounded {
  sourceText: string;
  section?: string | null;
}

export interface RequirementClaim extends SourceGrounded {
  requirement: string;
}

export interface ResponsibilityClaim extends SourceGrounded {
  responsibility: string;
}

/** Mirrors ai-service/app/agents/role_intelligence_schema.py's
 * RoleExtractionLLMOutput, camelCased at the ai-service.client.ts boundary. */
export interface RoleExtractionPayload {
  roleTitle?: string | null;
  mustHaveRequirements: RequirementClaim[];
  niceToHaveRequirements: RequirementClaim[];
  responsibilities: ResponsibilityClaim[];
  unparsedSections: string[];
}

export interface JobRoleExtraction {
  id: string;
  tenantId: string;
  jobRoleId: string;
  attempt: number;
  status: ExtractionStatus;
  extraction: RoleExtractionPayload | null;
  modelVersion: string | null;
  errorCode: string | null;
  errorMessage: string | null;
  startedAt: string | null;
  completedAt: string | null;
  createdAt: string;
}

export interface JobRole {
  id: string;
  tenantId: string;
  title: string;
  department: string | null;
  location: string | null;
  employmentType: string | null;
  seniority: string | null;
  status: JobRoleStatus;
  jdSourceType: JdSourceType;
  jdText: string | null;
  jdFileName: string | null;
  activeExtraction: JobRoleExtraction | null;
  createdBy: string;
  closedAt: string | null;
  createdAt: string;
  updatedAt: string;
}
