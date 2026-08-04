-- Auth + RBAC schema migration (Prisma-aligned).
-- Generated for HireOS platform auth module.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TYPE "UserStatus" AS ENUM ('ACTIVE', 'INVITED', 'DISABLED');
CREATE TYPE "InvitationStatus" AS ENUM ('PENDING', 'ACCEPTED', 'REVOKED', 'EXPIRED');

-- Drop legacy Sprint-1 shapes if present (fresh local DBs / reset).
DROP TABLE IF EXISTS "audit_events" CASCADE;
DROP TABLE IF EXISTS "users" CASCADE;
DROP TABLE IF EXISTS "tenants" CASCADE;
DROP TYPE IF EXISTS "UserRole";

CREATE TABLE "tenants" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "name" TEXT NOT NULL,
    "domain" TEXT NOT NULL,
    "logo_url" TEXT,
    "settings_json" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "tenants_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "tenants_domain_key" ON "tenants"("domain");

CREATE TABLE "users" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "email" TEXT NOT NULL,
    "password_hash" TEXT,
    "status" "UserStatus" NOT NULL DEFAULT 'ACTIVE',
    "sso_provider" TEXT,
    "sso_id" TEXT,
    "is_mfa_enabled" BOOLEAN NOT NULL DEFAULT false,
    "last_login_at" TIMESTAMP(3),
    "last_login_ip" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "users_email_key" ON "users"("email");
CREATE INDEX "users_sso_provider_sso_id_idx" ON "users"("sso_provider", "sso_id");

CREATE TABLE "user_profiles" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "user_id" UUID NOT NULL,
    "first_name" TEXT,
    "last_name" TEXT,
    "phone" TEXT,
    "avatar_url" TEXT,
    "job_title" TEXT,
    "preferences_json" JSONB NOT NULL DEFAULT '{}',
    CONSTRAINT "user_profiles_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "user_profiles_user_id_key" ON "user_profiles"("user_id");
ALTER TABLE "user_profiles" ADD CONSTRAINT "user_profiles_user_id_fkey"
  FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

CREATE TABLE "permissions" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "slug" TEXT NOT NULL,
    "module" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    CONSTRAINT "permissions_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "permissions_slug_key" ON "permissions"("slug");
CREATE INDEX "permissions_module_idx" ON "permissions"("module");

CREATE TABLE "roles" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "tenant_id" UUID NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "is_system_role" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "roles_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "roles_tenant_id_idx" ON "roles"("tenant_id");
CREATE UNIQUE INDEX "roles_tenant_id_name_key" ON "roles"("tenant_id", "name");
ALTER TABLE "roles" ADD CONSTRAINT "roles_tenant_id_fkey"
  FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;

CREATE TABLE "role_permissions" (
    "role_id" UUID NOT NULL,
    "permission_id" UUID NOT NULL,
    CONSTRAINT "role_permissions_pkey" PRIMARY KEY ("role_id", "permission_id")
);

ALTER TABLE "role_permissions" ADD CONSTRAINT "role_permissions_role_id_fkey"
  FOREIGN KEY ("role_id") REFERENCES "roles"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "role_permissions" ADD CONSTRAINT "role_permissions_permission_id_fkey"
  FOREIGN KEY ("permission_id") REFERENCES "permissions"("id") ON DELETE CASCADE ON UPDATE CASCADE;

CREATE TABLE "tenant_user_roles" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "tenant_id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "role_id" UUID NOT NULL,
    "assigned_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "scope_json" JSONB,
    CONSTRAINT "tenant_user_roles_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "tenant_user_roles_tenant_id_idx" ON "tenant_user_roles"("tenant_id");
CREATE INDEX "tenant_user_roles_user_id_idx" ON "tenant_user_roles"("user_id");
CREATE UNIQUE INDEX "tenant_user_roles_tenant_id_user_id_key" ON "tenant_user_roles"("tenant_id", "user_id");
ALTER TABLE "tenant_user_roles" ADD CONSTRAINT "tenant_user_roles_tenant_id_fkey"
  FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "tenant_user_roles" ADD CONSTRAINT "tenant_user_roles_user_id_fkey"
  FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "tenant_user_roles" ADD CONSTRAINT "tenant_user_roles_role_id_fkey"
  FOREIGN KEY ("role_id") REFERENCES "roles"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE TABLE "user_sessions" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "user_id" UUID NOT NULL,
    "tenant_id" UUID NOT NULL,
    "refresh_token_hash" TEXT NOT NULL,
    "user_agent" TEXT,
    "ip_address" TEXT,
    "expires_at" TIMESTAMP(3) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "revoked_at" TIMESTAMP(3),
    CONSTRAINT "user_sessions_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "user_sessions_user_id_idx" ON "user_sessions"("user_id");
CREATE INDEX "user_sessions_tenant_id_idx" ON "user_sessions"("tenant_id");
CREATE INDEX "user_sessions_refresh_token_hash_idx" ON "user_sessions"("refresh_token_hash");
ALTER TABLE "user_sessions" ADD CONSTRAINT "user_sessions_user_id_fkey"
  FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "user_sessions" ADD CONSTRAINT "user_sessions_tenant_id_fkey"
  FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;

CREATE TABLE "tenant_policies" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "tenant_id" UUID NOT NULL,
    "retention_days" INTEGER NOT NULL DEFAULT 90,
    "audio_storage_enabled" BOOLEAN NOT NULL DEFAULT false,
    "human_override_required" BOOLEAN NOT NULL DEFAULT true,
    "updated_by" UUID,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "tenant_policies_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "tenant_policies_tenant_id_key" ON "tenant_policies"("tenant_id");
ALTER TABLE "tenant_policies" ADD CONSTRAINT "tenant_policies_tenant_id_fkey"
  FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "tenant_policies" ADD CONSTRAINT "tenant_policies_updated_by_fkey"
  FOREIGN KEY ("updated_by") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

CREATE TABLE "tenant_invitations" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "tenant_id" UUID NOT NULL,
    "email" TEXT NOT NULL,
    "role_id" UUID NOT NULL,
    "token_hash" TEXT NOT NULL,
    "status" "InvitationStatus" NOT NULL DEFAULT 'PENDING',
    "invited_by" UUID NOT NULL,
    "expires_at" TIMESTAMP(3) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "accepted_at" TIMESTAMP(3),
    CONSTRAINT "tenant_invitations_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "tenant_invitations_tenant_id_email_idx" ON "tenant_invitations"("tenant_id", "email");
CREATE INDEX "tenant_invitations_token_hash_idx" ON "tenant_invitations"("token_hash");
ALTER TABLE "tenant_invitations" ADD CONSTRAINT "tenant_invitations_tenant_id_fkey"
  FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "tenant_invitations" ADD CONSTRAINT "tenant_invitations_role_id_fkey"
  FOREIGN KEY ("role_id") REFERENCES "roles"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
ALTER TABLE "tenant_invitations" ADD CONSTRAINT "tenant_invitations_invited_by_fkey"
  FOREIGN KEY ("invited_by") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

CREATE TABLE "password_reset_tokens" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "user_id" UUID NOT NULL,
    "token_hash" TEXT NOT NULL,
    "expires_at" TIMESTAMP(3) NOT NULL,
    "used_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "password_reset_tokens_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "password_reset_tokens_token_hash_idx" ON "password_reset_tokens"("token_hash");
CREATE INDEX "password_reset_tokens_user_id_idx" ON "password_reset_tokens"("user_id");
ALTER TABLE "password_reset_tokens" ADD CONSTRAINT "password_reset_tokens_user_id_fkey"
  FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

CREATE TABLE "audit_events" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "tenant_id" UUID NOT NULL,
    "actor_id" TEXT NOT NULL,
    "event_type" TEXT NOT NULL,
    "entity_type" TEXT NOT NULL,
    "entity_id" TEXT NOT NULL,
    "payload" JSONB NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "audit_events_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "audit_events_tenant_id_idx" ON "audit_events"("tenant_id");
CREATE INDEX "audit_events_tenant_id_entity_type_entity_id_idx" ON "audit_events"("tenant_id", "entity_type", "entity_id");
ALTER TABLE "audit_events" ADD CONSTRAINT "audit_events_tenant_id_fkey"
  FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- updated_at trigger helper
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tenants_set_updated_at
  BEFORE UPDATE ON tenants FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER users_set_updated_at
  BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER tenant_policies_set_updated_at
  BEFORE UPDATE ON tenant_policies FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Row Level Security (defense in depth; app still filters by tenant_id)
ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_roles ON roles
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));

CREATE POLICY tenant_isolation_memberships ON tenant_user_roles
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));

CREATE POLICY tenant_isolation_sessions ON user_sessions
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));

CREATE POLICY tenant_isolation_policies ON tenant_policies
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));

CREATE POLICY tenant_isolation_invitations ON tenant_invitations
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));

CREATE POLICY tenant_isolation_audit ON audit_events
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant_id', true), ''));

-- Global permission seed
INSERT INTO permissions (id, slug, module, description) VALUES
  (gen_random_uuid(), 'workspace.settings.read', 'workspace', 'View workspace branding and policies'),
  (gen_random_uuid(), 'workspace.settings.write', 'workspace', 'Update workspace branding and policies'),
  (gen_random_uuid(), 'members.read', 'members', 'List tenant members'),
  (gen_random_uuid(), 'members.invite', 'members', 'Invite members to the tenant'),
  (gen_random_uuid(), 'members.role.write', 'members', 'Change member roles'),
  (gen_random_uuid(), 'members.remove', 'members', 'Remove members from the tenant'),
  (gen_random_uuid(), 'roles.read', 'roles', 'View roles and permission matrix'),
  (gen_random_uuid(), 'roles.write', 'roles', 'Create and edit custom tenant roles'),
  (gen_random_uuid(), 'audit.read', 'audit', 'View audit events'),
  (gen_random_uuid(), 'profile.read', 'profile', 'Read own profile'),
  (gen_random_uuid(), 'profile.write', 'profile', 'Update own profile')
ON CONFLICT (slug) DO NOTHING;
