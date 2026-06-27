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

export interface MemberLoanRow {
  id: string;
  loan_reference: string;
  status: string;
  outstanding_principal: string;
}

const columns: DataTableProps<MemberLoanRow>["columns"] = [
  {
    id: "loan_reference",
    accessorKey: "loan_reference",
    header: "Reference",
    cell: ({ row }) => (
      <Link
        href={`/member/loans/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.loan_reference}
      </Link>
    ),
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
    cell: ({ row }) => (
      <StatusBadge entity="loan" status={row.original.status} />
    ),
  },
];

function sortRows(
  rows: MemberLoanRow[],
  column: string | null,
  dir: "asc" | "desc",
): MemberLoanRow[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof MemberLoanRow];
    const bv = b[column as keyof MemberLoanRow];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

export function MemberLoansTable({ rows }: { rows: MemberLoanRow[] }) {
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
    <DataTable<MemberLoanRow>
      id="member-loans"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{
        totalRows: rows.length,
        isError: false,
        isPermissionDenied: false,
      }}
      emptyState={{
        title: "No loans",
        description: "Your loans will appear here.",
      }}
    />
  );
}
