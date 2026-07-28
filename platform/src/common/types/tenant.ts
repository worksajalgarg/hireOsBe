export enum UserRole {
  Recruiter = "recruiter",
  HiringManager = "hiring_manager",
  Admin = "admin",
  Auditor = "auditor",
}

export enum UserStatus {
  Active = "ACTIVE",
  Invited = "INVITED",
  Disabled = "DISABLED",
}

export interface Tenant {
  id: string;
  name: string;
  domain: string;
  logoUrl?: string | null;
  settingsJson?: Record<string, unknown>;
  createdAt: string;
  updatedAt?: string;
}

export interface UserProfile {
  id: string;
  userId: string;
  firstName?: string | null;
  lastName?: string | null;
  phone?: string | null;
  avatarUrl?: string | null;
  jobTitle?: string | null;
  preferencesJson?: Record<string, unknown>;
}

export interface User {
  id: string;
  email: string;
  status: UserStatus | string;
  isMfaEnabled: boolean;
  createdAt: string;
  /** Active tenant context when returned from /users/me or login. */
  tenantId?: string;
  role?: UserRole | string;
  roleName?: string;
  permissions?: string[];
  profile?: UserProfile | null;
}

export interface AuthTokens {
  accessToken: string;
  expiresIn: number;
  tokenType: "Bearer";
}

export interface LoginResponse extends AuthTokens {
  user: User;
  tenant: Tenant;
}

export interface WorkspaceSettings {
  tenant: Tenant;
  policy: {
    id: string;
    tenantId: string;
    retentionDays: number;
    audioStorageEnabled: boolean;
    humanOverrideRequired: boolean;
    updatedAt: string;
  };
}

export interface TeamMember {
  userId: string;
  email: string;
  status: string;
  roleId: string;
  roleName: string;
  firstName?: string | null;
  lastName?: string | null;
  joinedAt: string;
}

export interface RoleMatrixItem {
  id: string;
  name: string;
  description?: string | null;
  isSystemRole: boolean;
  permissions: string[];
}
