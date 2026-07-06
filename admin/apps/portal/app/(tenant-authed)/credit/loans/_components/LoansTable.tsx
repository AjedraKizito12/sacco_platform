// admin/apps/portal/app/(tenant-authed)/credit/loans/_components/LoansTable.tsx
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

export interface LoanRow {
  id: string;
  loan_reference: string;
  member_label: string;
  principal_amount: string;
  outstanding_principal: string;
  status: string;
}

const columns: DataTableProps<LoanRow>["columns"] = [
  {
    id: "loan_reference",
    accessorKey: "loan_reference",
    header: "Reference",
    cell: ({ row }) => (
      <Link
        href={`/credit/loans/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        {row.original.loan_reference}
      </Link>
    ),
  },
  { id: "member_label", accessorKey: "member_label", header: "Member" },
  {
    id: "principal_amount",
    accessorKey: "principal_amount",
    header: "Principal",
    cell: ({ row }) => <Money amount={row.original.principal_amount} />,
  },
  {
    id: "outstanding_principal",
    accessorKey: "outstanding_principal",
    header: "Outstanding",
    cell: ({ row }) => <Money amount={row.original.outstanding_principal} />,
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="loan" status={row.original.status} />,
  },
];

function sortRows(
  rows: LoanRow[],
  column: string | null,
  dir: "asc" | "desc",
): LoanRow[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof LoanRow];
    const bv = b[column as keyof LoanRow];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

export function LoansTable({ rows }: { rows: LoanRow[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "loan_reference", direction: "asc" },
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
    <DataTable<LoanRow>
      id="loans"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No loans yet",
        description: "Disburse an approved application to create a loan.",
      }}
    />
  );
}
