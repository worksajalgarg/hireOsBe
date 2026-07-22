export type AuditEventType =
  | "tenant.created"
  | "user.invited"
  | "user.role_changed"
  | "role_context.approved"
  | "candidate.disposition"
  | "model_version.promoted";

export interface AuditEvent {
  id: string;
  tenantId: string;
  actorId: string;
  eventType: AuditEventType;
  entityType: string;
  entityId: string;
  payload: Record<string, unknown>;
  createdAt: string;
}
