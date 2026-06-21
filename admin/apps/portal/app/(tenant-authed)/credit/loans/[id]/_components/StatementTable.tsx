// admin/apps/portal/app/(tenant-authed)/credit/loans/[id]/_components/StatementTable.tsx
"use client";

import { useMemo } from "react";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  Money,
  useTableUrlState,
} from "@sacco/ui";
import type { StatementLineOut } from "@sacco/schemas";

// StatementLineOut has no id; DataTable's TData must extend { id: string }.
type StatementRow = StatementLineOut & { id: string };

const columns: DataTableProps<StatementRow>["columns"] = [
  {
    id: "date",
    accessorKey: "date",
    header: "Date",
    cell: ({ row }) => <FormattedDate value={row.original.date} />,
  },
  { id: "line_type", accessorKey: "line_type", header: "Type" },
  { id: "description", accessorKey: "description", header: "Description" },
  {
    id: "debit",
    accessorKey: "debit",
    header: "Debit",
    cell: ({ row }) => <Money amount={row.original.debit} />,
  },
  {
    id: "credit",
    accessorKey: "credit",
    header: "Credit",
    cell: ({ row }) => <Money amount={row.original.credit} />,
  },
  {
    id: "running_balance",
    accessorKey: "running_balance",
    header: "Balance",
    cell: ({ row }) => <Money amount={row.original.running_balance} />,
  },
];

export function StatementTable({ rows }: { rows: StatementLineOut[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 100 });
  const withIds = useMemo<StatementRow[]>(
    () => rows.map((r, i) => ({ ...r, id: String(i) })),
    [rows],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return withIds.slice(start, start + urlState.pageSize);
  }, [withIds, urlState.page, urlState.pageSize]);

  return (
    <DataTable<StatementRow>
      id="loan-statement"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No statement lines yet",
        description: "Statement entries appear here.",
      }}
    />
  );
}
