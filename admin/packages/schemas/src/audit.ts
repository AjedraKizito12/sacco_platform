// Mirrors app/platform_/audit/schemas.py. Dates are ISO strings over the wire.

export interface AuditEntryOut {
  id: string;
  table_name: string;
  record_id: string;
  operation: string; // insert | update | delete
  actor_type: string;
  actor_id: string | null;
  actor_label: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  occurred_at: string;
  request_id: string | null;
  impersonation_id: string | null;
}

export interface AuditLogPage {
  items: AuditEntryOut[];
  total: number;
  page: number;
  page_size: number;
}

export const AUDIT_OPERATION_OPTIONS = [
  { value: "insert", label: "Insert" },
  { value: "update", label: "Update" },
  { value: "delete", label: "Delete" },
] as const;
