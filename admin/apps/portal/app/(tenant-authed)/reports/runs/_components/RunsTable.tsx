// admin/apps/portal/app/(tenant-authed)/reports/runs/_components/RunsTable.tsx
"use client";

import { useMemo } from "react";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  FormattedDateTime,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import type { ReportRunOut } from "@sacco/schemas";

const columns: DataTableProps<ReportRunOut>["columns"] = [
  { id: "report_type", accessorKey: "report_type", header: "Report type" },
  {
    id: "as_of_date",
    accessorKey: "as_of_date",
    header: "As of",
    cell: ({ row }) => <FormattedDate value={row.original.as_of_date} />,
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="report_run" status={row.original.status} />,
  },
  {
    id: "started_at",
    accessorKey: "started_at",
    header: "Started",
    cell: ({ row }) => <FormattedDateTime value={row.original.started_at} />,
  },
  {
    id: "completed_at",
    accessorKey: "completed_at",
    header: "Completed",
    cell: ({ row }) =>
      row.original.completed_at ? (
        <FormattedDateTime value={row.original.completed_at} />
      ) : (
        "—"
      ),
  },
];

export function RunsTable({ rows }: { rows: ReportRunOut[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 50 });
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<ReportRunOut>
      id="report-runs"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No report runs yet",
        description: "Scheduled report runs appear here.",
      }}
    />
  );
}
