export type InterviewSessionStatus = "PENDING" | "ACTIVE" | "COMPLETED" | "FAILED";

export interface InterviewSession {
  id: string;
  tenantId: string;
  candidateRef: string;
  roomName: string;
  status: InterviewSessionStatus;
  recordingUrl?: string | null;
  startedAt?: string | null;
  endedAt?: string | null;
  createdAt: string;
}
