"use client";

import {
  Count,
  DataTable,
  type DataTableProps,
  useTableUrlState,
} from "@sacco/ui";
import type { RateLimitPolicyOut } from "@sacco/schemas";

interface PolicyRow extends RateLimitPolicyOut {
  id: string;
}

export function PolicyTable({ policies }: { policies: RateLimitPolicyOut[] }) {
  const urlState = useTableUrlState({
    shallow: false,
    defaultSort: { column: "name", direction: "asc" },
    defaultPageSize: 25,
    filterKeys: [],
  });

  const rows: PolicyRow[] = policies.map((p) => ({ ...p, id: p.name }));

  const columns: DataTableProps<PolicyRow>["columns"] = [
    {
      id: "name",
      accessorKey: "name",
      header: "Policy",
      cell: ({ row }) => (
        <span className="font-mono text-[13px]">{row.original.name}</span>
      ),
    },
    {
      id: "limit",
      accessorKey: "limit",
      header: "Limit",
      cell: ({ row }) => <Count value={row.original.limit} />,
    },
    {
      id: "window_seconds",
      accessorKey: "window_seconds",
      header: "Window",
      cell: ({ row }) => `${row.original.window_seconds}s`,
    },
  ];

  return (
    <DataTable<PolicyRow>
      id="platform-rate-limit-policies"
      columns={columns}
      data={rows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No policies",
        description: "The rate limiter has no configured policies.",
      }}
    />
  );
}
