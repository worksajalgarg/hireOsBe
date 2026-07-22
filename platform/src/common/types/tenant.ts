export enum UserRole {
  Recruiter = "recruiter",
  HiringManager = "hiring_manager",
  Admin = "admin",
  Auditor = "auditor",
}

export interface Tenant {
  id: string;
  name: string;
  domain: string;
  createdAt: string;
}

export interface User {
  id: string;
  tenantId: string;
  email: string;
  role: UserRole;
  createdAt: string;
}
