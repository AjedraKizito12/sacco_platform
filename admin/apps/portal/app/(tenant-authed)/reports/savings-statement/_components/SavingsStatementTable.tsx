// admin/apps/portal/app/(tenant-authed)/reports/savings-statement/_components/SavingsStatementTable.tsx
"use client";

import { useMemo } from "react";
import {
  DataTable,
  type DataTableProps,
  FormattedDateTime,
  Money,
  useTableUrlState,
} from "@sacco/ui";
import type { SavingsStatementLineOut } from "@sacco/schemas";

type Row = SavingsStatementLineOut & { id: string };

const columns: DataTableProps<Row>["columns"] = [
  {
    id: "posted_at",
    accessorKey: "posted_at",
    header: "Posted",
    cell: ({ row }) => <FormattedDateTime value={row.original.posted_at} />,
  },
  { id: "transaction_type", accessorKey: "transaction_type", header: "Type" },
  {
    id: "narration",
    accessorKey: "narration",
    header: "Narration",
    cell: ({ row }) => row.original.narration ?? "—",
  },
  {
    id: "amount",
    accessorKey: "amount",
    header: "Amount",
    cell: ({ row }) => <Money amount={row.original.amount} />,
  },
  {
    id: "running_balance",
    accessorKey: "running_balance",
    header: "Running balance",
    cell: ({ row }) => <Money amount={row.original.running_balance} />,
  },
];

export function SavingsStatementTable({ rows }: { rows: SavingsStatementLineOut[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 100 });
  const withIds = useMemo<Row[]>(() => rows.map((r, i) => ({ ...r, id: String(i) })), [rows]);
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return withIds.slice(start, start + urlState.pageSize);
  }, [withIds, urlState.page, urlState.pageSize]);

  return (
    <DataTable<Row>
      id="savings-statement"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No savings transactions",
        description: "Choose a member to view.",
      }}
    />
  );
}
