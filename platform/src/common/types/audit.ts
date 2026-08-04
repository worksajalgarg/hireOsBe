export type AuditEventType =
  | "tenant.created"
  | "user.invited"
  | "user.role_changed"
  | "user.removed"
  | "user.login"
  | "user.logout"
  | "user.password_reset_requested"
  | "user.password_changed"
  | "workspace.settings_updated"
  | "role.created"
  | "role_context.approved"
  | "candidate.disposition"
  | "model_version.promoted"
  | "interview.session.created"
  | "interview.session.candidate_joined"
  | "interview.session.ended"
  | "interview.recording.started"
  | "interview.recording.completed"
  | "interview.transcript.ingested"
  | "prompt.template.created"
  | "prompt.template.updated"
  | "prompt.template.deleted";

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
