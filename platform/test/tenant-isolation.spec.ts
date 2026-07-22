import { Test } from "@nestjs/testing";
import { AuditService } from "../src/audit/audit.service";
import { PrismaService } from "../src/common/prisma.service";
import { TenantContextService } from "../src/common/tenant-context.service";

/**
 * Guards the Section 9 quality gate: "Security and tenant-isolation test
 * suite passes". This does not hit a real database — it verifies that
 * AuditService.listForTenant always filters by the caller's tenantId, so a
 * request scoped to tenant A can never observe tenant B's audit trail.
 */
describe("tenant isolation", () => {
  it("AuditService.listForTenant only queries events for the requesting tenant", async () => {
    const findMany = jest.fn().mockResolvedValue([]);
    const moduleRef = await Test.createTestingModule({
      providers: [
        AuditService,
        { provide: PrismaService, useValue: { auditEvent: { findMany, create: jest.fn() } } },
      ],
    }).compile();

    const auditService = moduleRef.get(AuditService);

    await auditService.listForTenant("tenant-a");

    expect(findMany).toHaveBeenCalledWith(
      expect.objectContaining({ where: { tenantId: "tenant-a" } }),
    );
    expect(findMany).not.toHaveBeenCalledWith(
      expect.objectContaining({ where: { tenantId: "tenant-b" } }),
    );
  });

  it("TenantContextService throws when no tenant header was set on the request", () => {
    const service = new TenantContextService({} as never);
    expect(() => service.getTenantId()).toThrow("Missing tenant context");
  });
});
