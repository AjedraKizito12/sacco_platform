// admin/apps/portal/app/(tenant-authed)/savings/accounts/[id]/_components/TransactionsTable.tsx
"use client";

import { useMemo } from "react";
import {
  DataTable,
  type DataTableProps,
  Money,
  useTableUrlState,
} from "@sacco/ui";
import type { SavingsTransactionOut } from "@sacco/schemas";

const columns: DataTableProps<SavingsTransactionOut>["columns"] = [
  { id: "transaction_type", accessorKey: "transaction_type", header: "Type" },
  {
    id: "amount",
    accessorKey: "amount",
    header: "Amount",
    cell: ({ row }) => <Money amount={row.original.amount} />,
  },
  {
    id: "narration",
    accessorKey: "narration",
    header: "Narration",
    cell: ({ row }) => row.original.narration ?? "—",
  },
];

export function TransactionsTable({ rows }: { rows: SavingsTransactionOut[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 25 });
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<SavingsTransactionOut>
      id="savings-transactions"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No transactions yet",
        description: "Deposits and withdrawals appear here.",
      }}
    />
  );
}
