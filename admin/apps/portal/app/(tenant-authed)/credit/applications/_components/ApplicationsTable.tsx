// admin/apps/portal/app/(tenant-authed)/credit/applications/_components/ApplicationsTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  Count,
  DataTable,
  type DataTableProps,
  Money,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";

export interface ApplicationRow {
  id: string;
  member_label: string;
  product_name: string;
  requested_amount: string;
  requested_term_periods: number;
  status: string;
}

const columns: DataTableProps<ApplicationRow>["columns"] = [
  {
    id: "member_label",
    accessorKey: "member_label",
    header: "Member",
    cell: ({ row }) => (
      <Link
        href={`/credit/applications/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        {row.original.member_label}
      </Link>
    ),
  },
  { id: "product_name", accessorKey: "product_name", header: "Product" },
  {
    id: "requested_amount",
    accessorKey: "requested_amount",
    header: "Amount",
    cell: ({ row }) => <Money amount={row.original.requested_amount} />,
  },
  {
    id: "requested_term_periods",
    accessorKey: "requested_term_periods",
    header: "Term",
    cell: ({ row }) => <Count value={row.original.requested_term_periods} />,
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge entity="loan_application" status={row.original.status} />
    ),
  },
];

function sortRows(
  rows: ApplicationRow[],
  column: string | null,
  dir: "asc" | "desc",
): ApplicationRow[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof ApplicationRow];
    const bv = b[column as keyof ApplicationRow];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

export function ApplicationsTable({ rows }: { rows: ApplicationRow[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "member_label", direction: "asc" },
    defaultPageSize: 25,
  });

  const sorted = useMemo(
    () => sortRows(rows, urlState.sortColumn, urlState.sortDirection),
    [rows, urlState.sortColumn, urlState.sortDirection],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<ApplicationRow>
      id="loan-applications"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No loan applications yet",
        description: "Submit an application to get started.",
      }}
    />
  );
}
