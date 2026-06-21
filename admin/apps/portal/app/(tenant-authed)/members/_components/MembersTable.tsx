// admin/apps/portal/app/(tenant-authed)/members/_components/MembersTable.tsx
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
import type { MemberOut } from "@sacco/schemas";

const STATUS_FILTER_OPTIONS = [
  "pending",
  "active",
  "suspended",
  "exited",
] as const;

const columns: DataTableProps<MemberOut>["columns"] = [
  {
    id: "member_number",
    accessorKey: "member_number",
    header: "Member #",
    cell: ({ row }) => (
      <Link
        href={`/members/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.member_number}
      </Link>
    ),
  },
  { id: "full_name", accessorKey: "full_name", header: "Name" },
  { id: "gender", accessorKey: "gender", header: "Gender" },
  {
    id: "phone",
    accessorKey: "phone",
    header: "Phone",
    cell: ({ row }) => row.original.phone ?? "—",
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="member" status={row.original.status} />,
  },
  {
    id: "joined_at",
    accessorKey: "joined_at",
    header: "Joined",
    cell: ({ row }) =>
      row.original.joined_at ? <FormattedDate value={row.original.joined_at} /> : "—",
  },
];

export function filterMembers(rows: MemberOut[], status: string | undefined): MemberOut[] {
  if (!status) return rows;
  return rows.filter((r) => r.status === status);
}

export function sortMembers(
  rows: MemberOut[],
  column: string | null,
  dir: "asc" | "desc",
): MemberOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof MemberOut];
    const bv = b[column as keyof MemberOut];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

/** Full (unpaginated) member list through DataTable; client-side filter/sort/paginate. */
export function MembersTable({ rows }: { rows: MemberOut[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "member_number", direction: "asc" },
    defaultPageSize: 25,
    filterKeys: ["status"],
  });

  const filtered = useMemo(
    () => filterMembers(rows, urlState.filters["status"]),
    [rows, urlState.filters],
  );
  const sorted = useMemo(
    () => sortMembers(filtered, urlState.sortColumn, urlState.sortDirection),
    [filtered, urlState.sortColumn, urlState.sortDirection],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<MemberOut>
      id="tenant-members"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: filtered.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No members yet",
        description: "Register a member to get started.",
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
