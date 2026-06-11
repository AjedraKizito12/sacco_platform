"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  RelativeTime,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import type { PlatformUserOut } from "@sacco/schemas";

const ROLE_LABELS: Record<PlatformUserOut["role"], string> = {
  superuser: "Superuser",
  admin: "Admin",
  finance: "Finance",
  support: "Support",
};

// ColumnDef is a dep of @sacco/ui (@tanstack/react-table), not the portal.
// Derive the column type from the exported DataTableProps to avoid a
// direct @tanstack/react-table import in the portal app.
const columns: DataTableProps<PlatformUserOut>["columns"] = [
  {
    id: "email",
    accessorKey: "email",
    header: "Email",
    cell: ({ row }) => (
      <Link
        href={`/platform/users/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.email}
      </Link>
    ),
  },
  { id: "full_name", accessorKey: "full_name", header: "Name" },
  {
    id: "role",
    accessorKey: "role",
    header: "Role",
    cell: ({ row }) => ROLE_LABELS[row.original.role],
  },
  {
    id: "is_active",
    accessorKey: "is_active",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge
        entity="platform_user"
        status={row.original.is_active ? "active" : "inactive"}
      />
    ),
  },
  {
    id: "last_login_at",
    accessorKey: "last_login_at",
    header: "Last login",
    cell: ({ row }) =>
      row.original.last_login_at ? (
        <RelativeTime value={row.original.last_login_at} />
      ) : (
        <span className="text-[var(--text-tertiary)]">Never</span>
      ),
  },
  {
    id: "created_at",
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => <FormattedDate value={row.original.created_at} />,
  },
];

export function sortRows(
  rows: PlatformUserOut[],
  column: string | null,
  dir: "asc" | "desc",
): PlatformUserOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof PlatformUserOut];
    const bv = b[column as keyof PlatformUserOut];
    const as = av === null ? "" : String(av);
    const bs = bv === null ? "" : String(bv);
    return as.localeCompare(bs);
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

/**
 * Renders the full (unpaginated) platform-user list through DataTable.
 * Pagination/sort are applied client-side over `rows` because
 * GET /platform/users does not accept paging params.
 */
export function UsersTable({ rows }: { rows: PlatformUserOut[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "email", direction: "asc" },
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
    <DataTable<PlatformUserOut>
      id="platform-users"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{
        totalRows: rows.length,
        isError: false,
        isPermissionDenied: false,
      }}
      emptyState={{
        title: "No platform users",
        description: "Create the first platform user to get started.",
      }}
    />
  );
}
