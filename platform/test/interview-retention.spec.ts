import { Test } from "@nestjs/testing";
import { InterviewRetentionService } from "../src/interviews/interview-retention.service";
import { PrismaService } from "../src/common/prisma.service";

describe("InterviewRetentionService", () => {
  it("deletes transcripts/summaries older than each tenant's own retentionDays", async () => {
    const findMany = jest.fn().mockResolvedValue([
      { tenantId: "tenant-a", retentionDays: 30 },
      { tenantId: "tenant-b", retentionDays: 90 },
    ]);
    const deleteTranscripts = jest.fn().mockResolvedValue({ count: 2 });
    const deleteSummaries = jest.fn().mockResolvedValue({ count: 1 });

    const moduleRef = await Test.createTestingModule({
      providers: [
        InterviewRetentionService,
        {
          provide: PrismaService,
          useValue: {
            tenantPolicy: { findMany },
            interviewTranscript: { deleteMany: deleteTranscripts },
            interviewSummary: { deleteMany: deleteSummaries },
          },
        },
      ],
    }).compile();

    const service = moduleRef.get(InterviewRetentionService);
    await service.cleanupExpiredTranscripts();

    expect(deleteTranscripts).toHaveBeenCalledTimes(2);
    expect(deleteTranscripts).toHaveBeenCalledWith(
      expect.objectContaining({ where: expect.objectContaining({ tenantId: "tenant-a" }) }),
    );
    expect(deleteTranscripts).toHaveBeenCalledWith(
      expect.objectContaining({ where: expect.objectContaining({ tenantId: "tenant-b" }) }),
    );
    expect(deleteSummaries).toHaveBeenCalledTimes(2);
  });
});
