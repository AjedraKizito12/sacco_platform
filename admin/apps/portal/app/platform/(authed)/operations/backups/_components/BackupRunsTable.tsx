"use client";

import {
  DataTable,
  type DataTableProps,
  FormattedDateTime,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import type { BackupRunOut } from "@sacco/schemas";

function formatBytes(n: number | null): string {
  if (n === null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = n;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function formatDuration(start: string, end: string | null): string {
  if (end === null) return "—";
  const ms = Date.parse(end) - Date.parse(start);
  if (Number.isNaN(ms) || ms < 0) return "—";
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

export function BackupRunsTable({ rows }: { rows: BackupRunOut[] }) {
  const urlState = useTableUrlState({
    shallow: false,
    defaultSort: { column: "created_at", direction: "desc" },
    defaultPageSize: 25,
    filterKeys: [],
  });

  const columns: DataTableProps<BackupRunOut>["columns"] = [
    {
      id: "created_at",
      accessorKey: "created_at",
      header: "Started",
      cell: ({ row }) => (
        <FormattedDateTime value={row.original.started_at} />
      ),
    },
    {
      id: "backup_type",
      accessorKey: "backup_type",
      header: "Type",
      cell: ({ row }) => (
        <span className="capitalize">{row.original.backup_type}</span>
      ),
    },
    {
      id: "status",
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => (
        <StatusBadge entity="backup_run" status={row.original.status} />
      ),
    },
    {
      id: "repo_size_bytes",
      accessorKey: "repo_size_bytes",
      header: "Repo size",
      cell: ({ row }) => formatBytes(row.original.repo_size_bytes),
    },
    {
      id: "duration",
      header: "Duration",
      enableSorting: false,
      cell: ({ row }) =>
        formatDuration(row.original.started_at, row.original.finished_at),
    },
  ];

  return (
    <DataTable<BackupRunOut>
      id="platform-backup-runs"
      columns={columns}
      data={rows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No backup runs yet",
        description:
          "Scheduled and on-demand base backups appear here once the backup sidecar has run.",
      }}
    />
  );
}
