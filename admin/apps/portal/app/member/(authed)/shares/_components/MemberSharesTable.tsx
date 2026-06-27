"use client";

import { useMemo } from "react";
import {
  Count,
  DataTable,
  type DataTableProps,
  Money,
  useTableUrlState,
} from "@sacco/ui";

export interface MemberShareRow {
  id: string;
  product_name: string;
  shares_held: number;
  total_value: string;
}

const columns: DataTableProps<MemberShareRow>["columns"] = [
  { id: "product_name", accessorKey: "product_name", header: "Product" },
  {
    id: "shares_held",
    accessorKey: "shares_held",
    header: "Shares held",
    cell: ({ row }) => <Count value={row.original.shares_held} />,
  },
  {
    id: "total_value",
    accessorKey: "total_value",
    header: "Total value",
    cell: ({ row }) => <Money amount={row.original.total_value} />,
  },
];

export function MemberSharesTable({ rows }: { rows: MemberShareRow[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "product_name", direction: "asc" },
    defaultPageSize: 25,
  });

  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<MemberShareRow>
      id="member-shares"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{
        totalRows: rows.length,
        isError: false,
        isPermissionDenied: false,
      }}
      emptyState={{
        title: "No share accounts",
        description: "Your share holdings will appear here.",
      }}
    />
  );
}
