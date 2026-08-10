import type { EvaluationRecommendation, EvidenceStrength } from "./evaluation";

/**
 * Scoped-down evaluation shape for interviews conducted before a real
 * rubric/role-context system exists (CandidateEvaluation in evaluation.ts
 * requires roleId/rubricVersion, which have nothing real to reference yet —
 * see docs/adr/0006-interview-transcript-storage.md). Reuses
 * EvaluationRecommendation/EvidenceStrength from evaluation.ts so ADR-0003's
 * "no bare score, always evidence-based" rule already holds today, and this
 * is forward-compatible: once a rubric system exists, add roleId/
 * rubricVersion and this maps directly onto CandidateEvaluation.
 */
export interface TopicEvaluation {
  topic: string;
  questionAsked: string;
  responseSummary: string;
  evidenceStrength: EvidenceStrength;
  supportingEvidence: string[];
  missingEvidence: string[];
}

export interface InterviewEvaluationSummary {
  candidateRef: string;
  recommendation: EvaluationRecommendation;
  overallAssessment: string;
  topics: TopicEvaluation[];
  modelVersion: string;
  generatedAt: string;
}
