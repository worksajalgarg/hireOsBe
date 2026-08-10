/** Hand-maintained duplicate of hireOsFe's lib/types/application.ts. */

export type ApplicationStage =
  | "APPLIED"
  | "SCREENING"
  | "SHORTLISTED"
  | "INTERVIEW_SCHEDULED"
  | "INTERVIEWED"
  | "OFFER";

export type ApplicationStatus = "ACTIVE" | "HIRED" | "REJECTED" | "WITHDRAWN";

/** Ordered funnel position — drives the pipeline UI's column order. */
export const APPLICATION_STAGES: ApplicationStage[] = [
  "APPLIED",
  "SCREENING",
  "SHORTLISTED",
  "INTERVIEW_SCHEDULED",
  "INTERVIEWED",
  "OFFER",
];

export interface ApplicationStageEvent {
  id: string;
  applicationId: string;
  fromStage: ApplicationStage | null;
  toStage: ApplicationStage;
  fromStatus: ApplicationStatus | null;
  toStatus: ApplicationStatus;
  actorId: string | null;
  note: string | null;
  createdAt: string;
}

export interface Application {
  id: string;
  tenantId: string;
  candidateId: string;
  jobRoleId: string;
  resumeId: string | null;
  stage: ApplicationStage;
  status: ApplicationStatus;
  stageEnteredAt: string;
  dispositionReason: string | null;
  assignedTo: string | null;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  /** Present on GET /job-roles/:jobRoleId/pipeline, which includes it —
   * absent on plain Application CRUD responses. */
  candidate?: { id: string; fullName: string };
}
