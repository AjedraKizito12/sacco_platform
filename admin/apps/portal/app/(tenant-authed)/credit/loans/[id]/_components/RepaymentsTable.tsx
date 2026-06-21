// admin/apps/portal/app/(tenant-authed)/credit/loans/[id]/_components/RepaymentsTable.tsx
"use client";

import { useMemo } from "react";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  Money,
  useTableUrlState,
} from "@sacco/ui";
import type { LoanRepaymentOut } from "@sacco/schemas";

const columns: DataTableProps<LoanRepaymentOut>["columns"] = [
  {
    id: "created_at",
    accessorKey: "created_at",
    header: "Date",
    cell: ({ row }) => <FormattedDate value={row.original.created_at} />,
  },
  {
    id: "amount",
    accessorKey: "amount",
    header: "Amount",
    cell: ({ row }) => <Money amount={row.original.amount} />,
  },
  {
    id: "principal_applied",
    accessorKey: "principal_applied",
    header: "Principal",
    cell: ({ row }) => <Money amount={row.original.principal_applied} />,
  },
  {
    id: "interest_applied",
    accessorKey: "interest_applied",
    header: "Interest",
    cell: ({ row }) => <Money amount={row.original.interest_applied} />,
  },
  {
    id: "penalties_applied",
    accessorKey: "penalties_applied",
    header: "Penalties",
    cell: ({ row }) => <Money amount={row.original.penalties_applied} />,
  },
];

export function RepaymentsTable({ rows }: { rows: LoanRepaymentOut[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 50 });
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<LoanRepaymentOut>
      id="loan-repayments"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No repayments yet",
        description: "Recorded repayments appear here.",
      }}
    />
  );
}
