# ADR 0004 — Auth, RBAC, and Postgres RLS

## Status
Accepted

## Context
Sprint 1 trusted client headers (`x-tenant-id`, `x-actor-id`, `x-actor-role`) for identity.
The threat model requires server-verified sessions before real data. Product needs
multi-tenant memberships, JWT access/refresh, and normalized RBAC.

## Decision

### Identity model
- `users` are **global** (unique email). A person may belong to multiple tenants.
- Membership is `tenant_user_roles` (one role per tenant membership for MVP).
- System roles (Admin, Recruiter, Hiring Manager, Auditor) are seeded per tenant with
  `is_system_role = true`. Permissions are global; grants are per role.

### Tokens
- Access JWT (15m) as Bearer token; claims: `sub`, `tenantId`, `sessionId`, `permissions`.
- Refresh token as httpOnly Secure cookie; only the hash is stored in `user_sessions`.

### Data access
- Controllers → Services → `PrismaService` (no repository layer).
- Application queries always include `tenantId` filters.
- Postgres RLS policies use `current_setting('app.current_tenant_id', true)`.
- Nest sets that GUC after JWT verification via `PrismaService.setTenantContext`.
- Table owner may bypass RLS locally; production should use a non-owner DB role with
  `FORCE ROW LEVEL SECURITY` (follow-up infra task).

### SSO / MFA
- `SsoProvider` interface with a stub implementation (WorkOS deferred).
- MFA columns + `/mfa/verify` stub until TOTP enrollment ships.

## Consequences
- Existing Sprint-1 `User.tenantId` / `User.role` enum is removed; callers migrate to memberships.
- API routes move under global prefix `/api/v1`.
- Shared FE/BE types must stay in sync by hand.
