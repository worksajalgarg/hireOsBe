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
} as const;

export type PermissionSlug = (typeof PERMISSIONS)[keyof typeof PERMISSIONS];

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
  ],
  [SYSTEM_ROLE_NAMES.HiringManager]: [
    PERMISSIONS.WORKSPACE_SETTINGS_READ,
    PERMISSIONS.MEMBERS_READ,
    PERMISSIONS.ROLES_READ,
    PERMISSIONS.PROFILE_READ,
    PERMISSIONS.PROFILE_WRITE,
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
