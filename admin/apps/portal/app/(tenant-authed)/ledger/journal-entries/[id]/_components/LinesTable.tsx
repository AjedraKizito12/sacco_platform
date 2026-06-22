// admin/apps/portal/app/(tenant-authed)/ledger/journal-entries/[id]/_components/LinesTable.tsx
"use client";

import { DataTable, type DataTableProps, Money, useTableUrlState } from "@sacco/ui";
import type { JournalLineOut } from "@sacco/schemas";

const columns: DataTableProps<JournalLineOut>["columns"] = [
  { id: "account_id", accessorKey: "account_id", header: "Account" },
  {
    id: "debit_amount",
    header: "Debit",
    cell: ({ row }) => <Money amount={row.original.debit_amount} />,
  },
  {
    id: "credit_amount",
    header: "Credit",
    cell: ({ row }) => <Money amount={row.original.credit_amount} />,
  },
  {
    id: "description",
    accessorKey: "description",
    header: "Description",
    cell: ({ row }) => row.original.description ?? "—",
  },
];

export function LinesTable({ rows }: { rows: JournalLineOut[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 100 });
  return (
    <DataTable<JournalLineOut>
      id="ledger-entry-lines"
      columns={columns}
      data={rows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{ title: "No lines", description: "This entry has no lines." }}
    />
  );
}
