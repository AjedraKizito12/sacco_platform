// admin/apps/portal/app/(tenant-authed)/fees/types/_components/FeeTypesTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  Money,
  useTableUrlState,
} from "@sacco/ui";
import type { FeeTypeOut } from "@sacco/schemas";

const columns: DataTableProps<FeeTypeOut>["columns"] = [
  { id: "code", accessorKey: "code", header: "Code" },
  {
    id: "name",
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => (
      <Link
        href={`/fees/types/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        {row.original.name}
      </Link>
    ),
  },
  { id: "applicable_to", accessorKey: "applicable_to", header: "Applies to" },
  {
    id: "amount",
    accessorKey: "amount",
    header: "Amount",
    cell: ({ row }) => <Money amount={row.original.amount} />,
  },
  { id: "trigger_kind", accessorKey: "trigger_kind", header: "Trigger" },
  {
    id: "is_active",
    accessorKey: "is_active",
    header: "Active",
    cell: ({ row }) => (row.original.is_active ? "Yes" : "No"),
  },
];

function sortRows(
  rows: FeeTypeOut[],
  column: string | null,
  dir: "asc" | "desc",
): FeeTypeOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof FeeTypeOut];
    const bv = b[column as keyof FeeTypeOut];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

export function FeeTypesTable({ rows }: { rows: FeeTypeOut[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "code", direction: "asc" },
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
    <DataTable<FeeTypeOut>
      id="fee-types"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No fee types yet",
        description: "Create a fee type to start assessing fees.",
      }}
    />
  );
}
