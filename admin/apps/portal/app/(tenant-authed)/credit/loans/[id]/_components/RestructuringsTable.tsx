// admin/apps/portal/app/(tenant-authed)/credit/loans/[id]/_components/RestructuringsTable.tsx
"use client";

import { useMemo } from "react";
import {
  Count,
  DataTable,
  type DataTableProps,
  FormattedDate,
  useTableUrlState,
} from "@sacco/ui";
import type { RestructuringOut } from "@sacco/schemas";

const columns: DataTableProps<RestructuringOut>["columns"] = [
  { id: "restructuring_type", accessorKey: "restructuring_type", header: "Type" },
  {
    id: "periods_added",
    accessorKey: "periods_added",
    header: "Periods added",
    cell: ({ row }) => <Count value={row.original.periods_added} />,
  },
  {
    id: "new_term_periods",
    accessorKey: "new_term_periods",
    header: "New term",
    cell: ({ row }) => <Count value={row.original.new_term_periods} />,
  },
  {
    id: "new_maturity_date",
    accessorKey: "new_maturity_date",
    header: "New maturity",
    cell: ({ row }) => <FormattedDate value={row.original.new_maturity_date} />,
  },
  {
    id: "executed_at",
    accessorKey: "executed_at",
    header: "Executed",
    cell: ({ row }) => <FormattedDate value={row.original.executed_at} />,
  },
];

export function RestructuringsTable({ rows }: { rows: RestructuringOut[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 25 });
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<RestructuringOut>
      id="loan-restructurings"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No restructurings yet",
        description: "Approved restructurings appear here.",
      }}
    />
  );
}
