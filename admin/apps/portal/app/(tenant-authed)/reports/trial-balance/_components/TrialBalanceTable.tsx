// admin/apps/portal/app/(tenant-authed)/reports/trial-balance/_components/TrialBalanceTable.tsx
"use client";

import { useMemo } from "react";
import {
  DataTable,
  type DataTableProps,
  Money,
  useTableUrlState,
} from "@sacco/ui";
import type { TrialBalanceLineOut } from "@sacco/schemas";

type Row = TrialBalanceLineOut & { id: string };

const columns: DataTableProps<Row>["columns"] = [
  { id: "account_code", accessorKey: "account_code", header: "Code" },
  { id: "account_name", accessorKey: "account_name", header: "Name" },
  { id: "account_type", accessorKey: "account_type", header: "Type" },
  {
    id: "debit_total",
    accessorKey: "debit_total",
    header: "Debit",
    cell: ({ row }) => <Money amount={row.original.debit_total} />,
  },
  {
    id: "credit_total",
    accessorKey: "credit_total",
    header: "Credit",
    cell: ({ row }) => <Money amount={row.original.credit_total} />,
  },
  {
    id: "balance",
    accessorKey: "balance",
    header: "Balance",
    cell: ({ row }) => <Money amount={row.original.balance} />,
  },
];

export function TrialBalanceTable({ rows }: { rows: TrialBalanceLineOut[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 100 });
  const withIds = useMemo<Row[]>(() => rows.map((r, i) => ({ ...r, id: String(i) })), [rows]);
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return withIds.slice(start, start + urlState.pageSize);
  }, [withIds, urlState.page, urlState.pageSize]);

  return (
    <DataTable<Row>
      id="trial-balance"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No trial-balance lines",
        description: "No data for the selected date.",
      }}
    />
  );
}
