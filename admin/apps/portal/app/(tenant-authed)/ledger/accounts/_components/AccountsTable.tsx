// admin/apps/portal/app/(tenant-authed)/ledger/accounts/_components/AccountsTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import { DataTable, type DataTableProps, useTableUrlState } from "@sacco/ui";
import type { AccountOut } from "@sacco/schemas";

const columns: DataTableProps<AccountOut>["columns"] = [
  {
    id: "code",
    accessorKey: "code",
    header: "Code",
    cell: ({ row }) => (
      <Link
        href={`/ledger/accounts/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        {row.original.code}
      </Link>
    ),
  },
  { id: "name", accessorKey: "name", header: "Name" },
  { id: "account_type", accessorKey: "account_type", header: "Type" },
  {
    id: "is_active",
    accessorKey: "is_active",
    header: "Active",
    cell: ({ row }) => (row.original.is_active ? "Yes" : "No"),
  },
];

function sortRows(rows: AccountOut[], column: string | null, dir: "asc" | "desc"): AccountOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof AccountOut];
    const bv = b[column as keyof AccountOut];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

export function AccountsTable({ rows }: { rows: AccountOut[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "code", direction: "asc" },
    defaultPageSize: 50,
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
    <DataTable<AccountOut>
      id="ledger-accounts"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No accounts yet",
        description: "Create an account to build the chart of accounts.",
      }}
    />
  );
}
