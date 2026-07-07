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

export interface ApprovalRow {
  id: string;
  operation_type: string;
  operation_label: string;
  status: string;
  current_approvals: number;
  required_approvals: number;
  requested_by_label: string;
  requested_at: string;
}

const STATUS_FILTER_OPTIONS = [
  "pending",
  "approved",
  "rejected",
  "executed",
  "execution_failed",
  "expired",
  "cancelled",
] as const;

const columns: DataTableProps<ApprovalRow>["columns"] = [
  {
    id: "operation_label",
    accessorKey: "operation_label",
    header: "Operation",
    cell: ({ row }) => (
      <Link
        href={`/approvals/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        {row.original.operation_label}
      </Link>
    ),
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="approval_request" status={row.original.status} />,
  },
  {
    id: "quorum",
    accessorKey: "current_approvals",
    header: "Quorum",
    enableSorting: false,
    cell: ({ row }) => (
      <span className="tabular-nums">
        {row.original.current_approvals} of {row.original.required_approvals}
      </span>
    ),
  },
  { id: "requested_by_label", accessorKey: "requested_by_label", header: "Requested by" },
  {
    id: "requested_at",
    accessorKey: "requested_at",
    header: "Requested",
    cell: ({ row }) => <FormattedDate value={row.original.requested_at} />,
  },
];

export function filterApprovals(rows: ApprovalRow[], status: string | undefined): ApprovalRow[] {
  if (!status) return rows;
  return rows.filter((r) => r.status === status);
}

export function sortApprovals(
  rows: ApprovalRow[],
  column: string | null,
  dir: "asc" | "desc",
): ApprovalRow[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) =>
    String(a[column as keyof ApprovalRow] ?? "").localeCompare(
      String(b[column as keyof ApprovalRow] ?? ""),
    ),
  );
  return dir === "desc" ? sorted.reverse() : sorted;
}

/** Full (unpaginated) approvals list through DataTable; client-side filter/sort/paginate. */
export function ApprovalsTable({ rows }: { rows: ApprovalRow[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "requested_at", direction: "desc" },
    defaultPageSize: 25,
    filterKeys: ["status"],
  });

  const filtered = useMemo(
    () => filterApprovals(rows, urlState.filters["status"]),
    [rows, urlState.filters],
  );
  const sorted = useMemo(
    () => sortApprovals(filtered, urlState.sortColumn, urlState.sortDirection),
    [filtered, urlState.sortColumn, urlState.sortDirection],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<ApprovalRow>
      id="tenant-approvals"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: filtered.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No approval requests",
        description:
          "Maker-checker requests from members, savings, shares, credit, and ledger flows appear here.",
      }}
      filterSlot={
        <Select
          value={urlState.filters["status"] ?? "all"}
          onValueChange={(v) => urlState.setFilter("status", v === "all" ? null : v)}
        >
          <SelectTrigger className="w-48" aria-label="Filter by status">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUS_FILTER_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    />
  );
}
