import { AuditBar, type AuditBarEntry } from "@sacco/ui";
import type { AuditLogPage } from "@sacco/schemas";
import { getPlatformPageContext } from "@/auth/server-page-context";
import { AUDIT_TABLE_BY_ENTITY } from "@/lib/audit-tables";

/**
 * Server component that fetches a record's most recent audit entries and
 * renders the live `<AuditBar>`. Falls back to the `<AuditBar>` placeholder
 * when the entityType has no known table mapping or the fetch fails.
 */
export async function AuditBarConnected({
  entityType,
  entityId,
}: {
  entityType: string;
  entityId: string;
}) {
  const table = AUDIT_TABLE_BY_ENTITY[entityType];
  if (!table) return <AuditBar entityType={entityType} entityId={entityId} />;

  const { resources } = await getPlatformPageContext();
  const { data } = await (
    resources.audit.listPlatform({
      table_name: table,
      record_id: entityId,
      page_size: 5,
    }) as Promise<{ data?: AuditLogPage; error?: unknown }>
  );
  if (!data) return <AuditBar entityType={entityType} entityId={entityId} />;

  const entries: AuditBarEntry[] = data.items.map((e) => ({
    id: e.id,
    operation: e.operation,
    actorLabel: e.actor_label,
    occurredAt: e.occurred_at,
  }));
  const viewAllHref = `/platform/audit?f_table_name=${table}&f_record_id=${entityId}`;

  return (
    <AuditBar
      entityType={entityType}
      entityId={entityId}
      entries={entries}
      viewAllHref={viewAllHref}
    />
  );
}
