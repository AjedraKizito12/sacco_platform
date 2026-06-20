/**
 * Maps a portal `entityType` (the semantic name used on detail pages and by
 * StatusBadge) to the physical `audit_log.table_name` written by the backend
 * `AuditableMixin` (which records `table_name = __tablename__`).
 */
export const AUDIT_TABLE_BY_ENTITY: Record<string, string> = {
  subscription: "subscriptions",
  subscription_plan: "subscription_plans",
  invoice: "invoices",
  platform_user: "platform_users",
  tenant: "tenants",
  approval_request: "approval_requests",
};
