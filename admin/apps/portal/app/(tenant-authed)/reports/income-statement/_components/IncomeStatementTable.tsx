// admin/apps/portal/app/(tenant-authed)/reports/income-statement/_components/IncomeStatementTable.tsx
"use client";

import { useMemo } from "react";
import {
  DataTable,
  type DataTableProps,
  Money,
  useTableUrlState,
} from "@sacco/ui";
import type { IncomeStatementLineOut } from "@sacco/schemas";

type Row = IncomeStatementLineOut & { id: string };

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
    id: "net_movement",
    accessorKey: "net_movement",
    header: "Net movement",
    cell: ({ row }) => <Money amount={row.original.net_movement} />,
  },
];

export function IncomeStatementTable({ rows }: { rows: IncomeStatementLineOut[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 100 });
  const withIds = useMemo<Row[]>(() => rows.map((r, i) => ({ ...r, id: String(i) })), [rows]);
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return withIds.slice(start, start + urlState.pageSize);
  }, [withIds, urlState.page, urlState.pageSize]);

  return (
    <DataTable<Row>
      id="income-statement"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No income-statement lines",
        description: "Choose a period to view.",
      }}
    />
  );
}
