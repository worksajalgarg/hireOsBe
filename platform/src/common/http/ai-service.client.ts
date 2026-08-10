import { Injectable, Logger } from "@nestjs/common";
import type {
  ResumeExtractionPayload,
  RoleExtractionPayload,
} from "../types";

export class UnsupportedFileTypeError extends Error {}
export class UnparsableDocumentError extends Error {}
export class FileTooLargeError extends Error {}
/** Timeouts and 502s from ai-service — worth a retry at the call site. */
export class AiServiceUnavailableError extends Error {}

// JSON shape from ai-service is intentionally loosely typed here —
// camelizeExtraction() is the one place field names/shapes are asserted.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type JsonRecord = Record<string, any>;

interface ResumeParseResult {
  extraction: ResumeExtractionPayload;
  sourceFilename: string;
  extractedTextLength: number;
  modelVersion: string;
}

interface RoleParseResult {
  extraction: RoleExtractionPayload;
  sourceFilename: string;
  extractedText: string;
  extractedTextLength: number;
  modelVersion: string;
}

/** Platform -> ai-service HTTP client. No precedent existed for this
 * direction before this feature — the only prior cross-service pattern was
 * ai-service calling back into platform (InternalServiceGuard). Uses Node's
 * global fetch/FormData/Blob rather than adding axios/@nestjs/axios, since
 * multipart forwarding needs no library beyond what the runtime provides. */
@Injectable()
export class AiServiceClient {
  private readonly logger = new Logger(AiServiceClient.name);
  private readonly baseUrl = requireEnv("AI_SERVICE_URL", "http://localhost:8000");
  private readonly timeoutMs = Number(process.env.AI_SERVICE_TIMEOUT_MS ?? 45_000);

  async parseResume(file: { buffer: Buffer; filename: string; mimetype: string }): Promise<ResumeParseResult> {
    const body = await this.postFile("/resume-intelligence/parse", file);
    const { source_filename, extracted_text_length, model_version, ...extraction } = body;
    return {
      extraction: camelizeExtraction(extraction) as unknown as ResumeExtractionPayload,
      sourceFilename: source_filename,
      extractedTextLength: extracted_text_length,
      modelVersion: model_version,
    };
  }

  async parseJobDescriptionFile(file: {
    buffer: Buffer;
    filename: string;
    mimetype: string;
  }): Promise<RoleParseResult> {
    const body = await this.postFile("/role-intelligence/parse", file);
    return this.toRoleParseResult(body);
  }

  /** ai-service only accepts file uploads — pasted JD text is synthesized
   * into a text/plain "file" rather than adding a second ai-service
   * endpoint just for the paste path. */
  async parseJobDescriptionText(text: string): Promise<RoleParseResult> {
    const body = await this.postFile("/role-intelligence/parse", {
      buffer: Buffer.from(text, "utf-8"),
      filename: "pasted-jd.txt",
      mimetype: "text/plain",
    });
    return this.toRoleParseResult(body);
  }

  private toRoleParseResult(body: JsonRecord): RoleParseResult {
    const { source_filename, extracted_text, extracted_text_length, model_version, ...extraction } = body;
    return {
      extraction: camelizeExtraction(extraction) as unknown as RoleExtractionPayload,
      sourceFilename: source_filename,
      extractedText: extracted_text,
      extractedTextLength: extracted_text_length,
      modelVersion: model_version,
    };
  }

  private async postFile(
    path: string,
    file: { buffer: Buffer; filename: string; mimetype: string },
  ): Promise<JsonRecord> {
    const form = new FormData();
    // Buffer is a Uint8Array subclass, a valid BlobPart — the explicit
    // Uint8Array wrap keeps this correct without pulling in DOM lib types.
    form.append("file", new Blob([new Uint8Array(file.buffer)], { type: file.mimetype }), file.filename);

    let res: Response;
    try {
      res = await fetch(`${this.baseUrl}${path}`, {
        method: "POST",
        body: form,
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      this.logger.error(`ai-service request to ${path} failed: ${(err as Error).message}`);
      throw new AiServiceUnavailableError("ai-service is unreachable");
    }

    if (res.ok) {
      return (await res.json()) as JsonRecord;
    }

    const detail = (await res.json().catch(() => ({ detail: res.statusText }))) as { detail?: unknown };
    const message = typeof detail.detail === "string" ? detail.detail : res.statusText;

    if (res.status === 415) throw new UnsupportedFileTypeError(message);
    if (res.status === 422) throw new UnparsableDocumentError(message);
    if (res.status === 413) throw new FileTooLargeError(message);
    throw new AiServiceUnavailableError(`ai-service returned ${res.status}: ${message}`);
  }
}

/** Explicit snake_case -> camelCase mapping for the extraction payload
 * fields ai-service returns — not a generic deep-camelize, so a schema
 * drift on the ai-service side fails loudly here instead of silently
 * passing through mismatched field names. */
function camelizeExtraction(raw: JsonRecord): Record<string, unknown> {
  const claim = (c: JsonRecord) => ({
    ...Object.fromEntries(Object.entries(c).filter(([k]) => !["source_text", "years_experience"].includes(k))),
    sourceText: c.source_text,
    ...(c.years_experience !== undefined ? { yearsExperience: c.years_experience } : {}),
  });

  if ("candidate_name" in raw || "work_history" in raw) {
    return {
      candidateName: raw.candidate_name,
      location: raw.location,
      contact: raw.contact,
      professionalSummary: raw.professional_summary,
      workHistory: (raw.work_history ?? []).map((w: JsonRecord) => ({
        company: w.company,
        title: w.title,
        startDate: w.start_date,
        endDate: w.end_date,
        isCurrent: w.is_current,
        responsibilities: (w.responsibilities ?? []).map(claim),
        sourceText: w.source_text,
      })),
      skills: (raw.skills ?? []).map(claim),
      education: (raw.education ?? []).map(claim),
      certifications: (raw.certifications ?? []).map(claim),
      projects: (raw.projects ?? []).map(claim),
      awards: (raw.awards ?? []).map(claim),
      publications: (raw.publications ?? []).map(claim),
      languages: (raw.languages ?? []).map(claim),
      verificationTopics: raw.verification_topics ?? [],
      unparsedSections: (raw.unparsed_sections ?? []).map((u: JsonRecord) => ({
        sectionTitle: u.section_title,
        rawText: u.raw_text,
        hasContent: u.has_content,
      })),
    };
  }

  return {
    roleTitle: raw.role_title,
    mustHaveRequirements: (raw.must_have_requirements ?? []).map(claim),
    niceToHaveRequirements: (raw.nice_to_have_requirements ?? []).map(claim),
    responsibilities: (raw.responsibilities ?? []).map(claim),
    unparsedSections: raw.unparsed_sections ?? [],
  };
}

function requireEnv(name: string, devDefault?: string): string {
  const value = process.env[name] ?? devDefault;
  if (!value) {
    throw new Error(`Missing required env var ${name}`);
  }
  return value;
}
