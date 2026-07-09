// admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/_components/KycSubmissionsTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  FormattedDateTime,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import type { KycSubmissionListItemOut } from "@sacco/schemas";

const STATUS_FILTER_OPTIONS = ["pending", "approved", "rejected"] as const;

const columns: DataTableProps<KycSubmissionListItemOut>["columns"] = [
  {
    id: "member_number",
    accessorKey: "member_number",
    header: "Member #",
    cell: ({ row }) => (
      <Link
        href={`/members/kyc-submissions/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        {row.original.member_number}
      </Link>
    ),
  },
  { id: "full_name", accessorKey: "full_name", header: "Member" },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge entity="kyc_submission" status={row.original.status} />
    ),
  },
  {
    id: "submitted_at",
    accessorKey: "submitted_at",
    header: "Submitted",
    cell: ({ row }) => <FormattedDateTime value={row.original.submitted_at} />,
  },
];

export function filterKycSubmissions(
  rows: KycSubmissionListItemOut[],
  status: string | undefined,
): KycSubmissionListItemOut[] {
  if (!status) return rows;
  return rows.filter((r) => r.status === status);
}

export function sortKycSubmissions(
  rows: KycSubmissionListItemOut[],
  column: string | null,
  dir: "asc" | "desc",
): KycSubmissionListItemOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof KycSubmissionListItemOut];
    const bv = b[column as keyof KycSubmissionListItemOut];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

/** Full (unpaginated) submissions list through DataTable; client-side filter/sort/paginate. */
export function KycSubmissionsTable({ rows }: { rows: KycSubmissionListItemOut[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "submitted_at", direction: "desc" },
    defaultPageSize: 25,
    filterKeys: ["status"],
  });

  const filtered = useMemo(
    () => filterKycSubmissions(rows, urlState.filters["status"]),
    [rows, urlState.filters],
  );
  const sorted = useMemo(
    () => sortKycSubmissions(filtered, urlState.sortColumn, urlState.sortDirection),
    [filtered, urlState.sortColumn, urlState.sortDirection],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<KycSubmissionListItemOut>
      id="kyc-submissions"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: filtered.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No KYC submissions",
        description: "Member KYC submissions awaiting review will appear here.",
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
