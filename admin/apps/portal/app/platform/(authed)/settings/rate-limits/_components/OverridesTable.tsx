"use client";

import {
  Count,
  DataTable,
  type DataTableProps,
  useTableUrlState,
} from "@sacco/ui";
import type { RateLimitOverrideRow } from "@sacco/schemas";

export function OverridesTable({ rows }: { rows: RateLimitOverrideRow[] }) {
  const urlState = useTableUrlState({
    shallow: false,
    defaultSort: { column: "plan", direction: "asc" },
    defaultPageSize: 25,
    filterKeys: [],
  });

  const columns: DataTableProps<RateLimitOverrideRow>["columns"] = [
    {
      id: "plan",
      accessorKey: "plan",
      header: "Plan",
      cell: ({ row }) => (
        <span className="font-mono text-[13px]">{row.original.plan}</span>
      ),
    },
    {
      id: "policy",
      accessorKey: "policy",
      header: "Policy",
      cell: ({ row }) => (
        <span className="font-mono text-[13px]">{row.original.policy}</span>
      ),
    },
    {
      id: "limit",
      accessorKey: "limit",
      header: "Limit",
      cell: ({ row }) =>
        row.original.limit === null ? (
          <span className="text-[var(--text-secondary)]">—</span>
        ) : (
          <Count value={row.original.limit} />
        ),
    },
    {
      id: "window_seconds",
      accessorKey: "window_seconds",
      header: "Window",
      cell: ({ row }) =>
        row.original.window_seconds === null
          ? "—"
          : `${row.original.window_seconds}s`,
    },
  ];

  return (
    <DataTable<RateLimitOverrideRow>
      id="platform-rate-limit-overrides"
      columns={columns}
      data={rows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No plan overrides",
        description:
          "No subscription plan overrides the default limits. Plans without an override inherit the defaults above.",
      }}
    />
  );
}
