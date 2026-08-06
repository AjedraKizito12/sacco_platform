"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  Count,
  DataTable,
  type DataTableProps,
  RelativeTime,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const columns: DataTableProps<TenantOut>["columns"] = [
  {
    id: "name",
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => (
      <Link
        href={`/platform/tenants/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        {row.original.name}
      </Link>
    ),
  },
  { id: "slug", accessorKey: "slug", header: "Slug" },
  {
    id: "lifecycle_state",
    accessorKey: "lifecycle_state",
    header: "Lifecycle",
    cell: ({ row }) => (
      <StatusBadge entity="tenant_lifecycle" status={row.original.lifecycle_state} />
    ),
  },
  {
    id: "archive_size_bytes",
    accessorKey: "archive_size_bytes",
    header: "Archive size (bytes)",
    cell: ({ row }) =>
      row.original.archive_size_bytes !== null ? (
        <Count value={row.original.archive_size_bytes} />
      ) : (
        "—"
      ),
  },
  {
    id: "archived_at",
    accessorKey: "archived_at",
    header: "Archived",
    cell: ({ row }) =>
      row.original.archived_at ? (
        <RelativeTime value={row.original.archived_at} />
      ) : (
        "—"
      ),
  },
];

/**
 * The archived tenants list. Data comes pre-filtered from the server
 * (GET /platform/tenants?lifecycle_state=archived); sort/pagination are
 * client-side at operator scale, matching TenantsTable.
 */
export function ArchivedTenantsTable({ rows }: { rows: TenantOut[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "archived_at", direction: "desc" },
    defaultPageSize: 25,
  });

  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<TenantOut>
      id="platform-tenants-archived"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{
        totalRows: rows.length,
        isError: false,
        isPermissionDenied: false,
      }}
      emptyState={{
        title: "No archived tenants",
        description: "Tenants appear here once offboarding reaches the archived state.",
      }}
    />
  );
}
