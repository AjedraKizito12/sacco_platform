// admin/apps/portal/app/platform/(authed)/billing/plans/_components/PlansTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  Money,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import type { SubscriptionPlanOut } from "@sacco/schemas";

const columns: DataTableProps<SubscriptionPlanOut>["columns"] = [
  {
    id: "name",
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => (
      <Link
        href={`/platform/billing/plans/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.name}
      </Link>
    ),
  },
  { id: "code", accessorKey: "code", header: "Code" },
  {
    id: "base_price",
    accessorKey: "base_price",
    header: "Base price",
    cell: ({ row }) => (
      <Money amount={row.original.base_price} currency={row.original.currency} />
    ),
  },
  { id: "billing_period", accessorKey: "billing_period", header: "Period" },
  {
    id: "is_active",
    accessorKey: "is_active",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge
        entity="platform_user"
        status={row.original.is_active ? "active" : "inactive"}
      />
    ),
  },
];

export function sortPlans(
  rows: SubscriptionPlanOut[],
  column: string | null,
  dir: "asc" | "desc",
): SubscriptionPlanOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof SubscriptionPlanOut];
    const bv = b[column as keyof SubscriptionPlanOut];
    const as = av === null ? "" : String(av);
    const bs = bv === null ? "" : String(bv);
    return as.localeCompare(bs);
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

/**
 * Renders the full (unpaginated) plan list through DataTable. Sort +
 * pagination are client-side because GET /platform/billing/plans has no
 * paging params.
 */
export function PlansTable({ rows }: { rows: SubscriptionPlanOut[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "name", direction: "asc" },
    defaultPageSize: 25,
  });

  const sorted = useMemo(
    () => sortPlans(rows, urlState.sortColumn, urlState.sortDirection),
    [rows, urlState.sortColumn, urlState.sortDirection],
  );

  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<SubscriptionPlanOut>
      id="billing-plans"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No plans",
        description: "Create the first subscription plan to get started.",
      }}
    />
  );
}
