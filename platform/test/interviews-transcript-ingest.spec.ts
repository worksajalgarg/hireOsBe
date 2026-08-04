import { ForbiddenException, NotFoundException } from "@nestjs/common";
import { Test } from "@nestjs/testing";
import { InterviewsService } from "../src/interviews/interviews.service";
import { PrismaService } from "../src/common/prisma.service";
import { AuditService } from "../src/audit/audit.service";
import { LiveKitService } from "../src/interviews/livekit.service";
import { IngestTranscriptDto } from "../src/interviews/internal-dto";

const SESSION = { id: "session-1", tenantId: "tenant-a", roomName: "interview-1" };

function buildDto(overrides: Partial<IngestTranscriptDto> = {}): IngestTranscriptDto {
  return {
    tenantId: "tenant-a",
    lines: [{ speaker: "Candidate", text: "Hello", ts: 1 }],
    evaluation: {
      candidateRef: "cand-1",
      recommendation: "review",
      overallAssessment: "Solid candidate.",
      topics: [],
      modelVersion: "gemini-flash-latest",
      generatedAt: new Date().toISOString(),
    },
    promptVersionsUsed: { "candidate_interview": "v1" },
    modelUsage: {},
    ...overrides,
  } as IngestTranscriptDto;
}

async function buildService(prismaOverrides: Record<string, unknown> = {}) {
  const findUnique = jest.fn().mockResolvedValue(SESSION);
  const transaction = jest.fn().mockResolvedValue([{ id: "transcript-1" }, { id: "summary-1" }]);
  const record = jest.fn().mockResolvedValue(undefined);

  const moduleRef = await Test.createTestingModule({
    providers: [
      InterviewsService,
      {
        provide: PrismaService,
        useValue: {
          interviewSession: { findUnique },
          interviewTranscript: { upsert: jest.fn() },
          interviewSummary: { upsert: jest.fn() },
          $transaction: transaction,
          ...prismaOverrides,
        },
      },
      { provide: AuditService, useValue: { record } },
      { provide: LiveKitService, useValue: {} },
    ],
  }).compile();

  return {
    service: moduleRef.get(InterviewsService),
    findUnique,
    transaction,
    record,
  };
}

describe("InterviewsService.ingestTranscriptAndSummary", () => {
  it("upserts transcript + summary and records an audit event on success", async () => {
    const { service, transaction, record } = await buildService();

    const result = await service.ingestTranscriptAndSummary("session-1", buildDto());

    expect(transaction).toHaveBeenCalledTimes(1);
    expect(record).toHaveBeenCalledWith(
      expect.objectContaining({
        tenantId: "tenant-a",
        eventType: "interview.transcript.ingested",
        entityId: "session-1",
      }),
    );
    expect(result).toEqual({ transcriptId: "transcript-1", summaryId: "summary-1" });
  });

  it("rejects when the session belongs to a different tenant", async () => {
    const { service } = await buildService();

    await expect(
      service.ingestTranscriptAndSummary("session-1", buildDto({ tenantId: "tenant-b" })),
    ).rejects.toThrow(ForbiddenException);
  });

  it("rejects when the session doesn't exist", async () => {
    const { service, findUnique } = await buildService();
    findUnique.mockResolvedValueOnce(null);

    await expect(service.ingestTranscriptAndSummary("missing", buildDto())).rejects.toThrow(
      NotFoundException,
    );
  });
});
