// admin/apps/portal/app/(tenant-authed)/savings/_components/ProductsTable.tsx
"use client";

import { useMemo } from "react";
import {
  DataTable,
  type DataTableProps,
  Money,
  Percentage,
  useTableUrlState,
} from "@sacco/ui";
import type { SavingsProductOut } from "@sacco/schemas";

const columns: DataTableProps<SavingsProductOut>["columns"] = [
  { id: "name", accessorKey: "name", header: "Name" },
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
  {
    id: "is_active",
    accessorKey: "is_active",
    header: "Active",
    cell: ({ row }) => (row.original.is_active ? "Yes" : "No"),
  },
];

function sortProducts(
  rows: SavingsProductOut[],
  column: string | null,
  dir: "asc" | "desc",
): SavingsProductOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof SavingsProductOut];
    const bv = b[column as keyof SavingsProductOut];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

export function ProductsTable({ rows }: { rows: SavingsProductOut[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "name", direction: "asc" },
    defaultPageSize: 25,
  });

  const sorted = useMemo(
    () => sortProducts(rows, urlState.sortColumn, urlState.sortDirection),
    [rows, urlState.sortColumn, urlState.sortDirection],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<SavingsProductOut>
      id="savings-products"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No savings products yet",
        description: "Create a product to start opening accounts.",
      }}
    />
  );
}
