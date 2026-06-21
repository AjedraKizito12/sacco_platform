// admin/apps/portal/app/(tenant-authed)/credit/loans/[id]/_components/ScheduleTable.tsx
"use client";

import { useMemo } from "react";
import {
  Count,
  DataTable,
  type DataTableProps,
  FormattedDate,
  Money,
  useTableUrlState,
} from "@sacco/ui";
import type { LoanInstallmentOut } from "@sacco/schemas";

const columns: DataTableProps<LoanInstallmentOut>["columns"] = [
  {
    id: "period_number",
    accessorKey: "period_number",
    header: "#",
    cell: ({ row }) => <Count value={row.original.period_number} />,
  },
  {
    id: "due_date",
    accessorKey: "due_date",
    header: "Due",
    cell: ({ row }) => <FormattedDate value={row.original.due_date} />,
  },
  {
    id: "principal_due",
    accessorKey: "principal_due",
    header: "Principal due",
    cell: ({ row }) => <Money amount={row.original.principal_due} />,
  },
  {
    id: "interest_due",
    accessorKey: "interest_due",
    header: "Interest due",
    cell: ({ row }) => <Money amount={row.original.interest_due} />,
  },
  {
    id: "total_due",
    accessorKey: "total_due",
    header: "Total due",
    cell: ({ row }) => <Money amount={row.original.total_due} />,
  },
  { id: "status", accessorKey: "status", header: "Status" },
];

export function ScheduleTable({ rows }: { rows: LoanInstallmentOut[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 50 });
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<LoanInstallmentOut>
      id="loan-schedule"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No schedule yet",
        description: "The repayment schedule appears here once the loan is disbursed.",
      }}
    />
  );
}
