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

export interface MemberApplicationRow {
  id: string;
  loan_product_id: string;
  requested_amount: string;
  requested_term_periods: number;
  status: string;
}

const columns: DataTableProps<MemberApplicationRow>["columns"] = [
  {
    id: "requested_amount",
    accessorKey: "requested_amount",
    header: "Requested",
    cell: ({ row }) => (
      <Link
        href={`/member/loans/applications/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        <Money amount={row.original.requested_amount} />
      </Link>
    ),
  },
  {
    id: "requested_term_periods",
    accessorKey: "requested_term_periods",
    header: "Term",
    cell: ({ row }) => <span>{row.original.requested_term_periods} periods</span>,
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
  rows: MemberApplicationRow[],
  column: string | null,
  dir: "asc" | "desc",
): MemberApplicationRow[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof MemberApplicationRow];
    const bv = b[column as keyof MemberApplicationRow];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

export function MemberApplicationsTable({
  rows,
}: {
  rows: MemberApplicationRow[];
}) {
  const urlState = useTableUrlState({
    defaultSort: { column: "requested_amount", direction: "desc" },
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
    <DataTable<MemberApplicationRow>
      id="member-loan-applications"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No loan applications",
        description: "Applications you submit will appear here.",
      }}
    />
  );
}
