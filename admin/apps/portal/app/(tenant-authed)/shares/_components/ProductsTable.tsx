// admin/apps/portal/app/(tenant-authed)/shares/_components/ProductsTable.tsx
"use client";

import { useMemo } from "react";
import {
  Count,
  DataTable,
  type DataTableProps,
  Money,
  useTableUrlState,
} from "@sacco/ui";
import type { ShareProductOut } from "@sacco/schemas";

const columns: DataTableProps<ShareProductOut>["columns"] = [
  { id: "name", accessorKey: "name", header: "Name" },
  {
    id: "par_value",
    accessorKey: "par_value",
    header: "Par value",
    cell: ({ row }) => <Money amount={row.original.par_value} />,
  },
  {
    id: "minimum_shares",
    accessorKey: "minimum_shares",
    header: "Min shares",
    cell: ({ row }) => <Count value={row.original.minimum_shares} />,
  },
  {
    id: "maximum_shares",
    accessorKey: "maximum_shares",
    header: "Max shares",
    cell: ({ row }) =>
      row.original.maximum_shares == null ? (
        "—"
      ) : (
        <Count value={row.original.maximum_shares} />
      ),
  },
  {
    id: "is_active",
    accessorKey: "is_active",
    header: "Active",
    cell: ({ row }) => (row.original.is_active ? "Yes" : "No"),
  },
];

function sortProducts(
  rows: ShareProductOut[],
  column: string | null,
  dir: "asc" | "desc",
): ShareProductOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof ShareProductOut];
    const bv = b[column as keyof ShareProductOut];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

export function ProductsTable({ rows }: { rows: ShareProductOut[] }) {
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
    <DataTable<ShareProductOut>
      id="share-products"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No share products yet",
        description: "Create a product to start opening accounts.",
      }}
    />
  );
}
