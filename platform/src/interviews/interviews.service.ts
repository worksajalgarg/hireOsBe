import { BadRequestException, ForbiddenException, Injectable, NotFoundException } from "@nestjs/common";
import { randomBytes, randomUUID, createHash } from "crypto";
import { PrismaService } from "../common/prisma.service";
import { AuditService } from "../audit/audit.service";
import { LiveKitService } from "./livekit.service";

const INVITE_TOKEN_TTL_MS = 60 * 60 * 1000; // 1 hour — short-lived, single-use candidate join link
const RECRUITER_OBSERVER_TOKEN_TTL_SECONDS = 30 * 60;
const CANDIDATE_TOKEN_TTL_SECONDS = 60 * 60;

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

  /** Recruiter/admin-authed: creates the session, the LiveKit room, and the
   * single-use candidate invite link. */
  async createSession(params: { tenantId: string; actorId: string; candidateRef: string }) {
    const roomName = `interview-${randomUUID()}`;
    const inviteToken = randomBytes(32).toString("hex");
    const session = await this.prisma.interviewSession.create({
      data: {
        tenantId: params.tenantId,
        candidateRef: params.candidateRef,
        roomName,
        inviteTokenHash: this.hashToken(inviteToken),
        inviteExpiresAt: new Date(Date.now() + INVITE_TOKEN_TTL_MS),
      },
    });

    // Room metadata is how the voice agent worker (a separate process, dispatched
    // by livekit-server, never calling back into platform) learns which tenant
    // and session it's bound to — it must never see another candidate's data.
    await this.livekit.createRoom(
      roomName,
      { tenantId: params.tenantId, sessionId: session.id },
      INVITE_TOKEN_TTL_MS / 1000,
    );

    await this.audit.record({
      tenantId: params.tenantId,
      actorId: params.actorId,
      eventType: "interview.session.created",
      entityType: "interview_session",
      entityId: session.id,
      payload: { candidateRef: params.candidateRef, roomName },
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
      grant: { roomJoin: true, canPublish: true, canSubscribe: true },
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
