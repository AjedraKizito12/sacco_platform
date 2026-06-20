"use client";

import { useMemo } from "react";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import type { JwtKeyOut } from "@sacco/schemas";

const columns: DataTableProps<JwtKeyOut>["columns"] = [
  {
    id: "kid",
    accessorKey: "kid",
    header: "Key ID",
    cell: ({ row }) => <span className="font-mono text-[12px]">{row.original.kid}</span>,
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="jwt_key" status={row.original.status} />,
  },
  { id: "algorithm", accessorKey: "algorithm", header: "Algorithm" },
  { id: "audience", accessorKey: "audience", header: "Audience" },
  {
    id: "created_at",
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => <FormattedDate value={row.original.created_at} />,
  },
  {
    id: "activated_at",
    accessorKey: "activated_at",
    header: "Activated",
    cell: ({ row }) =>
      row.original.activated_at ? (
        <FormattedDate value={row.original.activated_at} />
      ) : (
        <span className="text-[var(--text-tertiary)]">—</span>
      ),
  },
  {
    id: "retired_at",
    accessorKey: "retired_at",
    header: "Retired",
    cell: ({ row }) =>
      row.original.retired_at ? (
        <FormattedDate value={row.original.retired_at} />
      ) : (
        <span className="text-[var(--text-tertiary)]">—</span>
      ),
  },
];

/** Read-only signing-key list through DataTable; client-side paginate. */
export function JwtKeysTable({ rows }: { rows: JwtKeyOut[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "created_at", direction: "desc" },
    defaultPageSize: 25,
  });

  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<JwtKeyOut>
      id="settings-jwt-keys"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No signing keys",
        description: "Signing keys appear here once configured.",
      }}
    />
  );
}
