// admin/apps/portal/app/(tenant-authed)/savings/accounts/_components/AccountsTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  Money,
  Percentage,
  useTableUrlState,
} from "@sacco/ui";

export interface AccountRow {
  id: string;
  member_label: string;
  product_name: string;
  interest_rate: string;
  minimum_balance: string;
}

const columns: DataTableProps<AccountRow>["columns"] = [
  {
    id: "member_label",
    accessorKey: "member_label",
    header: "Member",
    cell: ({ row }) => (
      <Link
        href={`/savings/accounts/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        {row.original.member_label}
      </Link>
    ),
  },
  { id: "product_name", accessorKey: "product_name", header: "Product" },
  {
    id: "interest_rate",
    accessorKey: "interest_rate",
    header: "Interest",
    cell: ({ row }) => <Percentage value={row.original.interest_rate} />,
  },
  {
    id: "minimum_balance",
    accessorKey: "minimum_balance",
    header: "Min balance",
    cell: ({ row }) => <Money amount={row.original.minimum_balance} />,
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
      id="savings-accounts"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No savings accounts yet",
        description: "Open an account from a member or here.",
      }}
    />
  );
}
