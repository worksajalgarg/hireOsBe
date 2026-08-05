export const PERMISSIONS = {
  WORKSPACE_SETTINGS_READ: "workspace.settings.read",
  WORKSPACE_SETTINGS_WRITE: "workspace.settings.write",
  MEMBERS_READ: "members.read",
  MEMBERS_INVITE: "members.invite",
  MEMBERS_ROLE_WRITE: "members.role.write",
  MEMBERS_REMOVE: "members.remove",
  ROLES_READ: "roles.read",
  ROLES_WRITE: "roles.write",
  AUDIT_READ: "audit.read",
  PROFILE_READ: "profile.read",
  PROFILE_WRITE: "profile.write",
  RESUMES_READ: "resumes.read",
  RESUMES_WRITE: "resumes.write",
  RESUMES_EXTRACT: "resumes.extract",
} as const;

export type PermissionSlug = (typeof PERMISSIONS)[keyof typeof PERMISSIONS];

export const PERMISSION_META: Record<
  PermissionSlug,
  { module: string; description: string }
> = {
  [PERMISSIONS.WORKSPACE_SETTINGS_READ]: {
    module: "workspace",
    description: "View workspace branding and policies",
  },
  [PERMISSIONS.WORKSPACE_SETTINGS_WRITE]: {
    module: "workspace",
    description: "Update workspace branding and policies",
  },
  [PERMISSIONS.MEMBERS_READ]: { module: "members", description: "List tenant members" },
  [PERMISSIONS.MEMBERS_INVITE]: {
    module: "members",
    description: "Invite members to the tenant",
  },
  [PERMISSIONS.MEMBERS_ROLE_WRITE]: {
    module: "members",
    description: "Change member roles",
  },
  [PERMISSIONS.MEMBERS_REMOVE]: {
    module: "members",
    description: "Remove members from the tenant",
  },
  [PERMISSIONS.ROLES_READ]: {
    module: "roles",
    description: "View roles and permission matrix",
  },
  [PERMISSIONS.ROLES_WRITE]: {
    module: "roles",
    description: "Create and edit custom tenant roles",
  },
  [PERMISSIONS.AUDIT_READ]: { module: "audit", description: "View audit events" },
  [PERMISSIONS.PROFILE_READ]: { module: "profile", description: "Read own profile" },
  [PERMISSIONS.PROFILE_WRITE]: { module: "profile", description: "Update own profile" },
  [PERMISSIONS.RESUMES_READ]: { module: "resumes", description: "List and view resumes" },
  [PERMISSIONS.RESUMES_WRITE]: {
    module: "resumes",
    description: "Upload, edit, and delete resumes",
  },
  [PERMISSIONS.RESUMES_EXTRACT]: {
    module: "resumes",
    description: "Run resume extraction pipeline",
  },
};

export const SYSTEM_ROLE_NAMES = {
  Admin: "Admin",
  Recruiter: "Recruiter",
  HiringManager: "Hiring Manager",
  Auditor: "Auditor",
} as const;

/** Permission matrix for seeded system roles. */
export const SYSTEM_ROLE_PERMISSIONS: Record<string, PermissionSlug[]> = {
  [SYSTEM_ROLE_NAMES.Admin]: Object.values(PERMISSIONS),
  [SYSTEM_ROLE_NAMES.Recruiter]: [
    PERMISSIONS.WORKSPACE_SETTINGS_READ,
    PERMISSIONS.MEMBERS_READ,
    PERMISSIONS.ROLES_READ,
    PERMISSIONS.PROFILE_READ,
    PERMISSIONS.PROFILE_WRITE,
    PERMISSIONS.RESUMES_READ,
    PERMISSIONS.RESUMES_WRITE,
    PERMISSIONS.RESUMES_EXTRACT,
  ],
  [SYSTEM_ROLE_NAMES.HiringManager]: [
    PERMISSIONS.WORKSPACE_SETTINGS_READ,
    PERMISSIONS.MEMBERS_READ,
    PERMISSIONS.ROLES_READ,
    PERMISSIONS.PROFILE_READ,
    PERMISSIONS.PROFILE_WRITE,
    PERMISSIONS.RESUMES_READ,
    PERMISSIONS.RESUMES_EXTRACT,
  ],
  [SYSTEM_ROLE_NAMES.Auditor]: [
    PERMISSIONS.WORKSPACE_SETTINGS_READ,
    PERMISSIONS.MEMBERS_READ,
    PERMISSIONS.ROLES_READ,
    PERMISSIONS.AUDIT_READ,
    PERMISSIONS.PROFILE_READ,
    PERMISSIONS.PROFILE_WRITE,
  ],
};

/** Legacy UserRole enum values → system role display names. */
export const LEGACY_ROLE_TO_SYSTEM_NAME: Record<string, string> = {
  admin: SYSTEM_ROLE_NAMES.Admin,
  recruiter: SYSTEM_ROLE_NAMES.Recruiter,
  hiring_manager: SYSTEM_ROLE_NAMES.HiringManager,
  auditor: SYSTEM_ROLE_NAMES.Auditor,
};
