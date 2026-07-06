"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  RelativeTime,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import { tenantUserRoleLabel, type TenantUserOut } from "@sacco/schemas";

export function sortRows(
  rows: TenantUserOut[],
  column: string | null,
  dir: "asc" | "desc",
): TenantUserOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof TenantUserOut];
    const bv = b[column as keyof TenantUserOut];
    const as = av === null ? "" : String(av);
    const bs = bv === null ? "" : String(bv);
    return as.localeCompare(bs);
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

/** Full (unpaginated) tenant-user list through DataTable; client-side sort/paginate. */
export function TenantUsersTable({
  rows,
  tenantId,
}: {
  rows: TenantUserOut[];
  tenantId: string;
}) {
  const columns: DataTableProps<TenantUserOut>["columns"] = [
    {
      id: "email",
      accessorKey: "email",
      header: "Email",
      cell: ({ row }) => (
        <Link
          href={`/platform/tenants/${tenantId}/users/${row.original.id}`}
          className="font-medium text-[var(--text-link)]"
        >
          {row.original.email}
        </Link>
      ),
    },
    { id: "full_name", accessorKey: "full_name", header: "Name" },
    {
      id: "is_admin",
      accessorKey: "is_admin",
      header: "Role",
      cell: ({ row }) => tenantUserRoleLabel(row.original.is_admin),
    },
    {
      id: "is_active",
      accessorKey: "is_active",
      header: "Status",
      cell: ({ row }) => (
        <StatusBadge
          entity="tenant_user"
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
  ];

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
    <DataTable<TenantUserOut>
      id="tenant-users"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No users yet",
        description: "Add a user to this tenant to get started.",
      }}
    />
  );
}
