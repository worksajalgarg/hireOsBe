import { BadRequestException, ForbiddenException, Injectable, NotFoundException } from "@nestjs/common";
import { randomBytes, randomUUID, createHash } from "crypto";
import { TrackSource } from "@livekit/protocol";
import { Prisma } from "@prisma/client";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";
import { LiveKitService } from "./livekit.service";
import { SessionType } from "./dto";
import { IngestTranscriptDto } from "./internal-dto";
import { signRoomMetadata } from "./room-metadata-signing";

const DEFAULT_SESSION_TYPE: SessionType = "candidate_interview";

const INVITE_TOKEN_TTL_MS = 60 * 60 * 1000; // 1 hour — short-lived, single-use candidate join link
const RECRUITER_OBSERVER_TOKEN_TTL_SECONDS = 30 * 60;
// 3 hours, not the interview's expected ~30-45min length — a token that
// expires mid-call would disconnect the candidate with no refresh mechanism
// in place. Generous headroom costs nothing (it's scoped to one room only).
const CANDIDATE_TOKEN_TTL_SECONDS = 3 * 60 * 60;

@Injectable()
export class InterviewsService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditService,
    private readonly livekit: LiveKitService,
  ) {}

  private hashToken(token: string): string {
    return createHash("sha256").update(token).digest("hex");
  }

  private recordingObjectKey(tenantId: string, sessionId: string): string {
    return `${tenantId}/${sessionId}/recording.mp4`;
  }

  /** Same shared secret Phase D's internal-service-guard.ts checks on
   * ai-service's inbound calls — see docs/adr/0006-interview-transcript-storage.md.
   * Read lazily (not cached at construction) so tests can set/unset it
   * per-case without needing to reconstruct the service. */
  private internalServiceSecret(): string {
    const secret = process.env.INTERNAL_SERVICE_SECRET;
    if (!secret) {
      throw new Error("INTERNAL_SERVICE_SECRET is not configured");
    }
    return secret;
  }

  /** Recruiter/admin-authed: creates the session, the LiveKit room, and the
   * single-use candidate invite link. */
  async createSession(params: {
    tenantId: string;
    actorId: string;
    candidateRef: string;
    resumeContext?: string;
    sessionType?: SessionType;
    promptId?: string;
  }) {
    let promptSnapshotJson: Record<string, unknown> | undefined = undefined;

    const db = this.prisma as unknown as {
      promptTemplate?: {
        findFirst(args: { where: Record<string, unknown> }): Promise<{
          id: string;
          title: string;
          conversationFlow?: string | null;
          openingInstructions?: string | null;
          silenceInstructions?: string | null;
          systemBoundaries?: string | null;
        } | null>;
      };
    };

    type PromptTemplateRecord = {
      id: string;
      title: string;
      conversationFlow?: string | null;
      openingInstructions?: string | null;
      silenceInstructions?: string | null;
      systemBoundaries?: string | null;
    };

    let template: PromptTemplateRecord | null = null;

    if (db.promptTemplate?.findFirst) {
      template = params.promptId
        ? await db.promptTemplate.findFirst({
            where: { id: params.promptId },
          })
        : null;

      if (!template) {
        template = await db.promptTemplate.findFirst({
          where: { isDefault: true },
        });
      }
    } else {
      try {
        if (params.promptId) {
          const rows = await this.prisma.$queryRaw<PromptTemplateRecord[]>`
            SELECT id, title,
                   conversation_flow as "conversationFlow",
                   opening_instructions as "openingInstructions",
                   silence_instructions as "silenceInstructions",
                   system_boundaries as "systemBoundaries"
            FROM prompt_templates
            WHERE id = ${params.promptId}
            LIMIT 1
          `;
          if (rows && rows.length > 0) template = rows[0];
        }
        if (!template) {
          const rows = await this.prisma.$queryRaw<PromptTemplateRecord[]>`
            SELECT id, title,
                   conversation_flow as "conversationFlow",
                   opening_instructions as "openingInstructions",
                   silence_instructions as "silenceInstructions",
                   system_boundaries as "systemBoundaries"
            FROM prompt_templates
            WHERE is_default = true
            LIMIT 1
          `;
          if (rows && rows.length > 0) template = rows[0];
        }
      } catch {
        // Table prompt_templates might not exist or raw query failed; template stays null
      }
    }

    if (template) {
      promptSnapshotJson = {
        id: template.id,
        title: template.title,
        conversationFlow: template.conversationFlow,
        openingInstructions: template.openingInstructions,
        silenceInstructions: template.silenceInstructions,
        systemBoundaries: template.systemBoundaries,
      };
    }

    const roomName = `interview-${randomUUID()}`;
    const inviteToken = randomBytes(32).toString("hex");
    const sessionData: Record<string, unknown> = {
      tenantId: params.tenantId,
      candidateRef: params.candidateRef,
      roomName,
      inviteTokenHash: this.hashToken(inviteToken),
      inviteExpiresAt: new Date(Date.now() + INVITE_TOKEN_TTL_MS),
    };
    if (params.promptId) {
      sessionData.promptId = params.promptId;
    }
    if (promptSnapshotJson !== undefined) {
      sessionData.promptSnapshotJson = promptSnapshotJson;
    }

    let session: { id: string };
    try {
      session = await this.prisma.interviewSession.create({
        data: sessionData as Prisma.InterviewSessionCreateInput,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (
        message.includes("Unknown argument `promptId`") ||
        message.includes("Unknown argument `promptSnapshotJson`")
      ) {
        delete sessionData.promptId;
        delete sessionData.promptSnapshotJson;
        session = await this.prisma.interviewSession.create({
          data: sessionData as Prisma.InterviewSessionCreateInput,
        });
        try {
          if (params.promptId || promptSnapshotJson) {
            const snapshotStr = promptSnapshotJson ? JSON.stringify(promptSnapshotJson) : null;
            await this.prisma.$executeRaw`
              UPDATE interview_sessions
              SET prompt_id = ${params.promptId ?? null},
                  prompt_snapshot_json = ${snapshotStr}::jsonb
              WHERE id = ${session.id}
            `;
          }
        } catch {
          // Ignore if prompt_id / prompt_snapshot_json columns don't exist in DB schema
        }
      } else {
        throw err;
      }
    }

    const sessionType = params.sessionType ?? DEFAULT_SESSION_TYPE;
    const metadataSignature = signRoomMetadata(this.internalServiceSecret(), {
      tenantId: params.tenantId,
      sessionId: session.id,
      sessionType,
      resumeContext: params.resumeContext,
    });

    const promptContext = promptSnapshotJson ? JSON.stringify(promptSnapshotJson) : undefined;

    await this.livekit.createRoom(
      roomName,
      {
        tenantId: params.tenantId,
        sessionId: session.id,
        resumeContext: params.resumeContext,
        promptContext,
        sessionType,
        metadataSignature,
      },
      INVITE_TOKEN_TTL_MS / 1000,
    );

    await this.audit.record({
      tenantId: params.tenantId,
      actorId: params.actorId,
      eventType: "interview.session.created",
      entityType: "interview_session",
      entityId: session.id,
      payload: { candidateRef: params.candidateRef, roomName, sessionType, promptId: params.promptId },
    });

    return { id: session.id, inviteToken };
  }

  /** Public/unauthenticated: candidate presents the invite token from their link.
   * The PENDING -> ACTIVE flip is a single conditional `updateMany` (not a
   * find-then-update) so two concurrent requests for the same token can't
   * both pass the check before either commits — Postgres row locking on the
   * UPDATE guarantees only one request's WHERE clause matches. */
  async joinSession(inviteToken: string) {
    const inviteTokenHash = this.hashToken(inviteToken);
    const { count } = await this.prisma.interviewSession.updateMany({
      where: {
        inviteTokenHash,
        status: "PENDING",
        inviteExpiresAt: { gt: new Date() },
      },
      data: { status: "ACTIVE", startedAt: new Date() },
    });

    if (count !== 1) {
      throw new BadRequestException("Invalid, expired, or already-used invite link");
    }

    const session = await this.prisma.interviewSession.findFirstOrThrow({
      where: { inviteTokenHash },
    });

    await this.audit.record({
      tenantId: session.tenantId,
      actorId: `candidate-${session.id}`,
      eventType: "interview.session.candidate_joined",
      entityType: "interview_session",
      entityId: session.id,
      payload: { roomName: session.roomName },
    });

    const token = await this.livekit.mintToken({
      identity: `candidate-${session.id}`,
      roomName: session.roomName,
      // canPublishSources is explicit least-privilege: camera+mic only, not
      // a blanket canPublish (which would also allow e.g. screen-share).
      grant: {
        roomJoin: true,
        canPublish: true,
        canPublishSources: [TrackSource.CAMERA, TrackSource.MICROPHONE],
        canSubscribe: true,
      },
      ttlSeconds: CANDIDATE_TOKEN_TTL_SECONDS,
    });

    const recordingKey = this.recordingObjectKey(session.tenantId, session.id);
    const { egressId } = await this.livekit.startRoomCompositeEgress(session.roomName, recordingKey);
    await this.prisma.interviewSession.update({
      where: { id: session.id },
      data: { egressId, recordingUrl: recordingKey },
    });

    await this.audit.record({
      tenantId: session.tenantId,
      actorId: `candidate-${session.id}`,
      eventType: "interview.recording.started",
      entityType: "interview_session",
      entityId: session.id,
      payload: { egressId, recordingKey },
    });

    return { livekitUrl: this.livekit.url, token, roomName: session.roomName };
  }

  /** Recruiter/admin-authed observer token — no publish, subscribe-only. */
  async mintRecruiterToken(params: { tenantId: string; actorId: string; sessionId: string }) {
    const session = await this.getTenantSession(params.tenantId, params.sessionId);
    const token = await this.livekit.mintToken({
      identity: params.actorId,
      roomName: session.roomName,
      grant: { roomJoin: true, canPublish: false, canSubscribe: true },
      ttlSeconds: RECRUITER_OBSERVER_TOKEN_TTL_SECONDS,
    });
    return { livekitUrl: this.livekit.url, token, roomName: session.roomName };
  }

  async endSession(params: { tenantId: string; actorId: string; sessionId: string }) {
    const session = await this.getTenantSession(params.tenantId, params.sessionId);
    if (session.status !== "ACTIVE") {
      throw new BadRequestException(`Cannot end a session in status ${session.status}`);
    }

    if (session.egressId) {
      await this.livekit.stopEgress(session.egressId);
      await this.audit.record({
        tenantId: params.tenantId,
        actorId: params.actorId,
        eventType: "interview.recording.completed",
        entityType: "interview_session",
        entityId: session.id,
        payload: { egressId: session.egressId, recordingUrl: session.recordingUrl },
      });
    }

    await this.prisma.interviewSession.update({
      where: { id: session.id },
      data: { status: "COMPLETED", endedAt: new Date() },
    });

    await this.audit.record({
      tenantId: params.tenantId,
      actorId: params.actorId,
      eventType: "interview.session.ended",
      entityType: "interview_session",
      entityId: session.id,
      payload: {},
    });

    return { ok: true };
  }

  /** Called once by ai-service's voice_agent worker after a call ends (see
   * docs/adr/0006-interview-transcript-storage.md) — never by a user-facing
   * client. Upserts rather than creates: a retried delivery (ai-service's
   * local outbox retry, see transcript_delivery.py) after a prior partial
   * success must not fail on the unique interviewSessionId constraint. */
  async ingestTranscriptAndSummary(sessionId: string, dto: IngestTranscriptDto) {
    const session = await this.getTenantSession(dto.tenantId, sessionId);

    // ai-service's voice_agent worker never learns the real candidateRef —
    // room metadata doesn't carry it (see interviews.service.ts's
    // createRoom call above) and it isn't PII this service needs to push
    // into the agent's context just for this. This InterviewSession row is
    // the authoritative source, so it always wins over whatever ai-service
    // sent (a session/room-name placeholder — see
    // ai-service/app/voice_agent/post_call_evaluation.py).
    const evaluation = { ...dto.evaluation, candidateRef: session.candidateRef };

    const [transcript, summary] = await this.prisma.$transaction([
      this.prisma.interviewTranscript.upsert({
        where: { interviewSessionId: session.id },
        create: {
          interviewSessionId: session.id,
          tenantId: session.tenantId,
          linesJson: dto.lines as unknown as Prisma.InputJsonValue,
        },
        update: {
          linesJson: dto.lines as unknown as Prisma.InputJsonValue,
        },
      }),
      this.prisma.interviewSummary.upsert({
        where: { interviewSessionId: session.id },
        create: {
          interviewSessionId: session.id,
          tenantId: session.tenantId,
          rollingSummaryText: dto.rollingSummary,
          evaluationJson: evaluation as unknown as Prisma.InputJsonValue,
          promptVersionsUsedJson: dto.promptVersionsUsed as Prisma.InputJsonValue,
          modelUsageJson: dto.modelUsage as Prisma.InputJsonValue,
        },
        update: {
          rollingSummaryText: dto.rollingSummary,
          evaluationJson: evaluation as unknown as Prisma.InputJsonValue,
          promptVersionsUsedJson: dto.promptVersionsUsed as Prisma.InputJsonValue,
          modelUsageJson: dto.modelUsage as Prisma.InputJsonValue,
        },
      }),
    ]);

    await this.audit.record({
      tenantId: session.tenantId,
      actorId: "ai-service",
      eventType: "interview.transcript.ingested",
      entityType: "interview_session",
      entityId: session.id,
      payload: { recommendation: dto.evaluation.recommendation, lineCount: dto.lines.length },
    });

    return { transcriptId: transcript.id, summaryId: summary.id };
  }

  private async getTenantSession(tenantId: string, sessionId: string) {
    const session = await this.prisma.interviewSession.findUnique({ where: { id: sessionId } });
    if (!session) {
      throw new NotFoundException("Interview session not found");
    }
    if (session.tenantId !== tenantId) {
      throw new ForbiddenException("Interview session belongs to a different tenant");
    }
    return session;
  }
}
