"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const STATUS_FILTER_OPTIONS = [
  "pending",
  "provisioning",
  "active",
  "failed",
  "suspended",
  "deprovisioning",
  "archived",
] as const;

// ColumnDef is a dep of @sacco/ui (@tanstack/react-table), not the portal.
// Derive the column type from the exported DataTableProps to avoid a
// direct @tanstack/react-table import in the portal app.
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
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="tenant" status={row.original.status} />,
  },
  {
    id: "created_at",
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => <FormattedDate value={row.original.created_at} />,
  },
];

export function filterTenants(
  rows: TenantOut[],
  status: string | undefined,
): TenantOut[] {
  if (!status) return rows;
  return rows.filter((t) => t.status === status);
}

export function sortTenants(
  rows: TenantOut[],
  column: string | null,
  dir: "asc" | "desc",
): TenantOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof TenantOut];
    const bv = b[column as keyof TenantOut];
    const as = av === null ? "" : String(av);
    const bs = bv === null ? "" : String(bv);
    return as.localeCompare(bs);
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

/**
 * Renders the full (unpaginated) tenant list through DataTable. Filter,
 * sort and pagination are client-side because GET /platform/tenants has no
 * paging params (the ?status= param exists but shallow nuqs state cannot
 * re-trigger the server fetch; client filtering is fine at operator scale).
 */
export function TenantsTable({ rows }: { rows: TenantOut[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "name", direction: "asc" },
    defaultPageSize: 25,
    filterKeys: ["status"],
  });

  const filtered = useMemo(
    () => filterTenants(rows, urlState.filters["status"]),
    [rows, urlState.filters],
  );

  const sorted = useMemo(
    () => sortTenants(filtered, urlState.sortColumn, urlState.sortDirection),
    [filtered, urlState.sortColumn, urlState.sortDirection],
  );

  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<TenantOut>
      id="platform-tenants"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{
        totalRows: filtered.length,
        isError: false,
        isPermissionDenied: false,
      }}
      emptyState={{
        title: "No tenants",
        description: "Provision the first tenant to get started.",
      }}
      filterSlot={
        <Select
          value={urlState.filters["status"] ?? "all"}
          onValueChange={(v) => urlState.setFilter("status", v === "all" ? null : v)}
        >
          <SelectTrigger className="w-44" aria-label="Filter by status">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUS_FILTER_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    />
  );
}
