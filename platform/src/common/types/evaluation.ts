/**
 * Mirrors the evaluation object shown in the PRD (Section 6.4). This is the
 * shape the AI service's Evaluation Engine must produce for every scored
 * criterion — score and evidence are always separate fields, never collapsed
 * into one opaque number. Kept in sync by hand with hireOsFe's copy in
 * lib/types/evaluation.ts.
 */
export type EvidenceStrength = "strong" | "moderate" | "weak" | "missing";

export interface CriterionEvaluation {
  criterionId: string;
  criterion: string;
  score: number;
  evidenceStrength: EvidenceStrength;
  confidence: "low" | "medium" | "high";
  supportingEvidence: string[];
  missingEvidence: string[];
  contradictions: string[];
  reviewFlag?: string;
}

export type EvaluationRecommendation =
  | "strong_review"
  | "review"
  | "further_assessment"
  | "insufficient_data";

export interface CandidateEvaluation {
  candidateId: string;
  roleId: string;
  rubricVersion: string;
  modelVersion: string;
  criteria: CriterionEvaluation[];
  recommendation: EvaluationRecommendation;
}
