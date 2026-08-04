import { ExecutionContext, UnauthorizedException } from "@nestjs/common";
import { InternalServiceGuard } from "../src/common/internal-service.guard";

function contextWithHeader(authorization?: string): ExecutionContext {
  return {
    switchToHttp: () => ({
      getRequest: () => ({ headers: { authorization } }),
    }),
  } as unknown as ExecutionContext;
}

describe("InternalServiceGuard", () => {
  const ORIGINAL_ENV = process.env.INTERNAL_SERVICE_SECRET;

  afterEach(() => {
    process.env.INTERNAL_SERVICE_SECRET = ORIGINAL_ENV;
  });

  it("throws when INTERNAL_SERVICE_SECRET is not configured", () => {
    delete process.env.INTERNAL_SERVICE_SECRET;
    const guard = new InternalServiceGuard();
    expect(() => guard.canActivate(contextWithHeader("Bearer anything"))).toThrow(
      UnauthorizedException,
    );
  });

  it("throws when the Authorization header is missing", () => {
    process.env.INTERNAL_SERVICE_SECRET = "test-secret";
    const guard = new InternalServiceGuard();
    expect(() => guard.canActivate(contextWithHeader(undefined))).toThrow(UnauthorizedException);
  });

  it("throws when the bearer token doesn't match the secret", () => {
    process.env.INTERNAL_SERVICE_SECRET = "test-secret";
    const guard = new InternalServiceGuard();
    expect(() => guard.canActivate(contextWithHeader("Bearer wrong-secret"))).toThrow(
      UnauthorizedException,
    );
  });

  it("allows a matching bearer token", () => {
    process.env.INTERNAL_SERVICE_SECRET = "test-secret";
    const guard = new InternalServiceGuard();
    expect(guard.canActivate(contextWithHeader("Bearer test-secret"))).toBe(true);
  });
});
