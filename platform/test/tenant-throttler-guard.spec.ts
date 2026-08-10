import { TenantThrottlerGuard } from "../src/common/tenant-throttler.guard";
import { TenantScopedRequest } from "../src/common/tenant-context.middleware";

type TestableGuard = {
  getTracker(req: Pick<TenantScopedRequest, "tenantId" | "ip">): Promise<string>;
};

describe("TenantThrottlerGuard", () => {
  // ThrottlerGuard's constructor requires options/storage/reflector deps we
  // don't need for this unit test — only getTracker's own logic is under
  // test, called directly rather than through Nest's DI.
  const guard = Object.create(TenantThrottlerGuard.prototype) as TestableGuard;

  it("tracks by tenantId when present", async () => {
    const tracker = await guard.getTracker({ tenantId: "tenant-a", ip: "1.2.3.4" });
    expect(tracker).toBe("tenant-a");
  });

  it("falls back to ip when tenantId is missing", async () => {
    const tracker = await guard.getTracker({ ip: "1.2.3.4" } as Pick<
      TenantScopedRequest,
      "tenantId" | "ip"
    >);
    expect(tracker).toBe("1.2.3.4");
  });

  it("falls back to a fixed string when neither is present", async () => {
    const tracker = await guard.getTracker(
      {} as Pick<TenantScopedRequest, "tenantId" | "ip">,
    );
    expect(tracker).toBe("unknown");
  });
});
