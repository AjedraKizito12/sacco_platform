"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  Money,
  useTableUrlState,
} from "@sacco/ui";

export interface MemberSavingsRow {
  id: string;
  product_name: string;
  available_balance: string;
  balance: string;
}

const columns: DataTableProps<MemberSavingsRow>["columns"] = [
  {
    id: "product_name",
    accessorKey: "product_name",
    header: "Account",
    cell: ({ row }) => (
      <Link
        href={`/member/savings/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        {row.original.product_name}
      </Link>
    ),
  },
  {
    id: "available_balance",
    accessorKey: "available_balance",
    header: "Available balance",
    cell: ({ row }) => <Money amount={row.original.available_balance} />,
  },
];

export function MemberSavingsTable({ rows }: { rows: MemberSavingsRow[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "product_name", direction: "asc" },
    defaultPageSize: 25,
  });

  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<MemberSavingsRow>
      id="member-savings"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{
        totalRows: rows.length,
        isError: false,
        isPermissionDenied: false,
      }}
      emptyState={{
        title: "No savings accounts",
        description: "Your savings accounts will appear here.",
      }}
    />
  );
}
