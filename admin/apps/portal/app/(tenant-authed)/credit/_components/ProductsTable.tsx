// admin/apps/portal/app/(tenant-authed)/credit/_components/ProductsTable.tsx
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
import type { LoanProductOut } from "@sacco/schemas";

const columns: DataTableProps<LoanProductOut>["columns"] = [
  {
    id: "name",
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => (
      <Link
        href={`/credit/products/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        {row.original.name}
      </Link>
    ),
  },
  {
    id: "annual_interest_rate",
    accessorKey: "annual_interest_rate",
    header: "Interest",
    cell: ({ row }) => <Percentage value={row.original.annual_interest_rate} />,
  },
  { id: "interest_method", accessorKey: "interest_method", header: "Method" },
  { id: "repayment_frequency", accessorKey: "repayment_frequency", header: "Frequency" },
  {
    id: "min_amount",
    accessorKey: "min_amount",
    header: "Min",
    cell: ({ row }) => <Money amount={row.original.min_amount} />,
  },
  {
    id: "max_amount",
    accessorKey: "max_amount",
    header: "Max",
    cell: ({ row }) => <Money amount={row.original.max_amount} />,
  },
  {
    id: "is_active",
    accessorKey: "is_active",
    header: "Active",
    cell: ({ row }) => (row.original.is_active ? "Yes" : "No"),
  },
];

function sortProducts(
  rows: LoanProductOut[],
  column: string | null,
  dir: "asc" | "desc",
): LoanProductOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof LoanProductOut];
    const bv = b[column as keyof LoanProductOut];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

export function ProductsTable({ rows }: { rows: LoanProductOut[] }) {
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
    <DataTable<LoanProductOut>
      id="loan-products"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No loan products yet",
        description: "Create a product to start taking applications.",
      }}
    />
  );
}
