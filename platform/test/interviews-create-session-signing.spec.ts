import { Test } from "@nestjs/testing";
import { InterviewsService } from "../src/interviews/interviews.service";
import { PrismaService } from "../src/common/prisma.service";
import { AuditService } from "../src/audit/audit.service";
import { LiveKitService } from "../src/interviews/livekit.service";
import { signRoomMetadata } from "../src/interviews/room-metadata-signing";

describe("InterviewsService.createSession — room metadata signing", () => {
  const ORIGINAL_SECRET = process.env.INTERNAL_SERVICE_SECRET;

  afterEach(() => {
    process.env.INTERNAL_SERVICE_SECRET = ORIGINAL_SECRET;
  });

  async function buildService() {
    const create = jest.fn().mockResolvedValue({ id: "session-1" });
    const createRoom = jest.fn().mockResolvedValue(undefined);
    const record = jest.fn().mockResolvedValue(undefined);

    const moduleRef = await Test.createTestingModule({
      providers: [
        InterviewsService,
        { provide: PrismaService, useValue: { interviewSession: { create } } },
        { provide: AuditService, useValue: { record } },
        { provide: LiveKitService, useValue: { createRoom } },
      ],
    }).compile();

    return { service: moduleRef.get(InterviewsService), createRoom };
  }

  it("includes a correct metadataSignature in the room metadata", async () => {
    process.env.INTERNAL_SERVICE_SECRET = "test-secret";
    const { service, createRoom } = await buildService();

    await service.createSession({
      tenantId: "tenant-a",
      actorId: "actor-1",
      candidateRef: "cand-1",
      resumeContext: "resume text",
    });

    expect(createRoom).toHaveBeenCalledTimes(1);
    const [, metadata] = createRoom.mock.calls[0];
    expect(metadata.metadataSignature).toBe(
      signRoomMetadata("test-secret", {
        tenantId: "tenant-a",
        sessionId: "session-1",
        sessionType: "candidate_interview",
        resumeContext: "resume text",
      }),
    );
  });

  it("throws if INTERNAL_SERVICE_SECRET is not configured", async () => {
    delete process.env.INTERNAL_SERVICE_SECRET;
    const { service } = await buildService();

    await expect(
      service.createSession({ tenantId: "tenant-a", actorId: "actor-1", candidateRef: "cand-1" }),
    ).rejects.toThrow("INTERNAL_SERVICE_SECRET");
  });
});
