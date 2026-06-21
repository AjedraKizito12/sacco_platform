// admin/apps/portal/app/(tenant-authed)/shares/accounts/[id]/_components/TransactionsTable.tsx
"use client";

import { useMemo } from "react";
import {
  Count,
  DataTable,
  type DataTableProps,
  Money,
  useTableUrlState,
} from "@sacco/ui";
import type { ShareTransactionOut } from "@sacco/schemas";

const columns: DataTableProps<ShareTransactionOut>["columns"] = [
  { id: "transaction_type", accessorKey: "transaction_type", header: "Type" },
  {
    id: "quantity",
    accessorKey: "quantity",
    header: "Quantity",
    cell: ({ row }) => <Count value={row.original.quantity} />,
  },
  {
    id: "amount",
    accessorKey: "amount",
    header: "Amount",
    cell: ({ row }) => <Money amount={row.original.amount} />,
  },
];

export function TransactionsTable({ rows }: { rows: ShareTransactionOut[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 25 });
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<ShareTransactionOut>
      id="share-transactions"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No transactions yet",
        description: "Purchases and redemptions appear here.",
      }}
    />
  );
}
