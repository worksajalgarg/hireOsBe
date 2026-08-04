import { Injectable, UnauthorizedException } from "@nestjs/common";

export interface SsoIdentity {
  provider: string;
  ssoId: string;
  email: string;
  firstName?: string;
  lastName?: string;
}

/** Abstraction for WorkOS / Auth0 — stubbed until infra is provisioned. */
export abstract class SsoProvider {
  abstract exchangeCode(provider: string, code: string): Promise<SsoIdentity>;
}

@Injectable()
export class StubSsoProvider extends SsoProvider {
  async exchangeCode(provider: string, code: string): Promise<SsoIdentity> {
    if (!code || code === "invalid") {
      throw new UnauthorizedException("SSO provider rejected the authorization code");
    }
    // Dev stub: code format "email:user@example.com" or any code maps to demo identity
    const email = code.includes("@") ? code.replace(/^email:/, "") : `sso-user@${provider}.example.com`;
    return {
      provider,
      ssoId: `stub-${provider}-${Buffer.from(email).toString("hex").slice(0, 16)}`,
      email,
      firstName: "SSO",
      lastName: "User",
    };
  }
}
