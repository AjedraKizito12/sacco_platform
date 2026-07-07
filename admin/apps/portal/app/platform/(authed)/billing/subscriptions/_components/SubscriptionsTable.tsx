// admin/apps/portal/app/platform/(authed)/billing/subscriptions/_components/SubscriptionsTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";

export interface SubscriptionRow {
  id: string;
  tenant_id: string;
  tenant_name: string;
  plan_id: string;
  plan_name: string;
  status: string;
  current_period_start: string;
  current_period_end: string;
  next_billing_date: string | null;
}

const STATUS_FILTER_OPTIONS = [
  "pending",
  "trialing",
  "active",
  "past_due",
  "suspended",
  "cancelled",
] as const;

const columns: DataTableProps<SubscriptionRow>["columns"] = [
  {
    id: "tenant_name",
    accessorKey: "tenant_name",
    header: "Tenant",
    cell: ({ row }) => (
      <Link
        href={`/platform/billing/subscriptions/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        {row.original.tenant_name}
      </Link>
    ),
  },
  { id: "plan_name", accessorKey: "plan_name", header: "Plan" },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="subscription" status={row.original.status} />,
  },
  {
    id: "current_period_end",
    accessorKey: "current_period_end",
    header: "Period ends",
    cell: ({ row }) => <FormattedDate value={row.original.current_period_end} />,
  },
  {
    id: "next_billing_date",
    accessorKey: "next_billing_date",
    header: "Next billing",
    cell: ({ row }) =>
      row.original.next_billing_date ? (
        <FormattedDate value={row.original.next_billing_date} />
      ) : (
        <span className="text-[var(--text-tertiary)]">—</span>
      ),
  },
];

export function filterSubscriptions(
  rows: SubscriptionRow[],
  status: string | undefined,
): SubscriptionRow[] {
  if (!status) return rows;
  return rows.filter((s) => s.status === status);
}

export function sortSubscriptions(
  rows: SubscriptionRow[],
  column: string | null,
  dir: "asc" | "desc",
): SubscriptionRow[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof SubscriptionRow];
    const bv = b[column as keyof SubscriptionRow];
    const as = av === null ? "" : String(av);
    const bs = bv === null ? "" : String(bv);
    return as.localeCompare(bs);
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

/**
 * Renders the full (unpaginated) subscription list through DataTable. Filter,
 * sort and pagination are client-side (GET /platform/billing/subscriptions has
 * no usable paging; status filter via shallow nuqs state — same as SP13).
 */
export function SubscriptionsTable({ rows }: { rows: SubscriptionRow[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "tenant_name", direction: "asc" },
    defaultPageSize: 25,
    filterKeys: ["status"],
  });

  const filtered = useMemo(
    () => filterSubscriptions(rows, urlState.filters["status"]),
    [rows, urlState.filters],
  );
  const sorted = useMemo(
    () => sortSubscriptions(filtered, urlState.sortColumn, urlState.sortDirection),
    [filtered, urlState.sortColumn, urlState.sortDirection],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<SubscriptionRow>
      id="billing-subscriptions"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: filtered.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No subscriptions",
        description: "Assign a plan to a tenant to create the first subscription.",
      }}
      filterSlot={
        <Select
          value={urlState.filters["status"] ?? "all"}
          onValueChange={(v) => urlState.setFilter("status", v === "all" ? null : v)}
        >
          <SelectTrigger className="w-44" aria-label="Filter by status">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUS_FILTER_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1).replace("_", " ")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    />
  );
}
