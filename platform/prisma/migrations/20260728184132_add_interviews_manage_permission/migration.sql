-- Add the interviews.manage permission (grants create/join LiveKit interview
-- sessions) and back-fill it onto every existing tenant's Admin, Recruiter,
-- and Hiring Manager system roles, matching SYSTEM_ROLE_PERMISSIONS in
-- src/common/permissions.ts.

INSERT INTO permissions (id, slug, module, description)
VALUES (gen_random_uuid(), 'interviews.manage', 'interviews', 'Create and join AI voice interview sessions')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
CROSS JOIN permissions p
WHERE p.slug = 'interviews.manage'
  AND r.name IN ('Admin', 'Recruiter', 'Hiring Manager')
ON CONFLICT (role_id, permission_id) DO NOTHING;
