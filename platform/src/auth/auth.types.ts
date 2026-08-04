export interface AuthJwtPayload {
  sub: string;
  tenantId: string;
  sessionId: string;
  roleName?: string;
  permissions: string[];
}

export const REFRESH_COOKIE_NAME = "hireos_refresh";
export const ACCESS_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60; // 7 days
export const REFRESH_TOKEN_TTL_MS = 30 * 24 * 60 * 60 * 1000;
