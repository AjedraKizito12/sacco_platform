import type { AuditLogPage } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { AuditTable } from "@/components/audit/AuditTable";

export const metadata = { title: "Audit" };

const FILTER_KEYS = [
  ["f_table_name", "table_name"],
  ["f_operation", "operation"],
  ["f_actor_id", "actor_id"],
  ["f_record_id", "record_id"],
  ["f_occurred_from", "occurred_from"],
  ["f_occurred_to", "occurred_to"],
] as const;

export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const { resources } = await getTenantPageContext();

  const one = (k: string): string | undefined =>
    typeof sp[k] === "string" ? (sp[k] as string) : undefined;

  const query: Record<string, unknown> = {
    page: Number(one("page") ?? "1"),
    page_size: Number(one("pageSize") ?? "25"),
  };
  for (const [spKey, apiKey] of FILTER_KEYS) {
    const v = one(spKey);
    if (v) query[apiKey] = v;
  }

  const { data } = await (resources.audit.listOperator(query) as Promise<{
    data?: AuditLogPage;
    error?: unknown;
  }>);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Audit log</h1>
      <AuditTable
        items={data?.items ?? []}
        total={data?.total ?? 0}
        tableId="tenant-audit"
        showImpersonation={false}
      />
    </div>
  );
}
