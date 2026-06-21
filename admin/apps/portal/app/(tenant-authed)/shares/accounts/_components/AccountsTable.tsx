// admin/apps/portal/app/(tenant-authed)/shares/accounts/_components/AccountsTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  Count,
  DataTable,
  type DataTableProps,
  Money,
  useTableUrlState,
} from "@sacco/ui";

export interface AccountRow {
  id: string;
  member_label: string;
  product_name: string;
  shares_held: number;
  total_value: string;
}

const columns: DataTableProps<AccountRow>["columns"] = [
  {
    id: "member_label",
    accessorKey: "member_label",
    header: "Member",
    cell: ({ row }) => (
      <Link
        href={`/shares/accounts/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.member_label}
      </Link>
    ),
  },
  { id: "product_name", accessorKey: "product_name", header: "Product" },
  {
    id: "shares_held",
    accessorKey: "shares_held",
    header: "Shares",
    cell: ({ row }) => <Count value={row.original.shares_held} />,
  },
  {
    id: "total_value",
    accessorKey: "total_value",
    header: "Value",
    cell: ({ row }) => <Money amount={row.original.total_value} />,
  },
];

function sortRows(
  rows: AccountRow[],
  column: string | null,
  dir: "asc" | "desc",
): AccountRow[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof AccountRow];
    const bv = b[column as keyof AccountRow];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

export function AccountsTable({ rows }: { rows: AccountRow[] }) {
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
    <DataTable<AccountRow>
      id="share-accounts"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No share accounts yet",
        description: "Open an account from a member or here.",
      }}
    />
  );
}
