-- Permission catalog (global). Idempotent seed for auth/RBAC.
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
