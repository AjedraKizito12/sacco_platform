"use client";

import { useMemo } from "react";
import {
  DataTable,
  type DataTableProps,
  Money,
  useTableUrlState,
} from "@sacco/ui";

export interface MemberTransactionRow {
  id: string;
  transaction_type: string;
  amount: string;
  narration: string | null;
}

const columns: DataTableProps<MemberTransactionRow>["columns"] = [
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

export function MemberTransactionsTable({
  rows,
}: {
  rows: MemberTransactionRow[];
}) {
  const urlState = useTableUrlState({ defaultPageSize: 25 });
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<MemberTransactionRow>
      id="member-savings-transactions"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{
        totalRows: rows.length,
        isError: false,
        isPermissionDenied: false,
      }}
      emptyState={{
        title: "No transactions yet",
        description: "Deposits and withdrawals appear here.",
      }}
    />
  );
}
