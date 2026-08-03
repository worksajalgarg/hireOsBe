import { Type } from "class-transformer";
import {
  IsArray,
  IsDateString,
  IsIn,
  IsNumber,
  IsObject,
  IsOptional,
  IsString,
  MinLength,
  ValidateNested,
} from "class-validator";
import type { EvaluationRecommendation, EvidenceStrength } from "../common/types/evaluation";

const EVALUATION_RECOMMENDATIONS: EvaluationRecommendation[] = [
  "strong_review",
  "review",
  "further_assessment",
  "insufficient_data",
];
const EVIDENCE_STRENGTHS: EvidenceStrength[] = ["strong", "moderate", "weak", "missing"];

export class TranscriptLineDto {
  @IsString()
  @MinLength(1)
  speaker!: string;

  @IsString()
  text!: string;

  @IsOptional()
  @IsString()
  stage?: string;

  @IsNumber()
  ts!: number;
}

export class TopicEvaluationDto {
  @IsString()
  @MinLength(1)
  topic!: string;

  @IsString()
  questionAsked!: string;

  @IsString()
  responseSummary!: string;

  @IsIn(EVIDENCE_STRENGTHS)
  evidenceStrength!: EvidenceStrength;

  @IsArray()
  @IsString({ each: true })
  supportingEvidence!: string[];

  @IsArray()
  @IsString({ each: true })
  missingEvidence!: string[];
}

export class InterviewEvaluationSummaryDto {
  @IsString()
  @MinLength(1)
  candidateRef!: string;

  @IsIn(EVALUATION_RECOMMENDATIONS)
  recommendation!: EvaluationRecommendation;

  @IsString()
  overallAssessment!: string;

  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => TopicEvaluationDto)
  topics!: TopicEvaluationDto[];

  @IsString()
  @MinLength(1)
  modelVersion!: string;

  @IsDateString()
  generatedAt!: string;
}

/** Posted once, at the end of a call, by ai-service's voice_agent worker
 * shutdown callback — see docs/adr/0006-interview-transcript-storage.md. */
export class IngestTranscriptDto {
  @IsString()
  @MinLength(1)
  tenantId!: string;

  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => TranscriptLineDto)
  lines!: TranscriptLineDto[];

  @IsOptional()
  @IsString()
  rollingSummary?: string;

  @ValidateNested()
  @Type(() => InterviewEvaluationSummaryDto)
  evaluation!: InterviewEvaluationSummaryDto;

  /** {agentDefinitionKey: promptVersion} — correlates a regression to an
   * exact prompt version. Free-form for now (no AgentDefinition table
   * exists yet — see Phase C, deferred). */
  @IsObject()
  promptVersionsUsed!: Record<string, string>;

  /** Per-use-case aggregate: provider/model/latency/fallback counts for
   * this session. Free-form — shape owned by ai-service's model_gateway. */
  @IsObject()
  modelUsage!: Record<string, unknown>;
}
