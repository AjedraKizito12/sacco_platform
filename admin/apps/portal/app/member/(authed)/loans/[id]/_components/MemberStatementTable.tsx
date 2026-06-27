"use client";

import { useMemo } from "react";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  Money,
  useTableUrlState,
} from "@sacco/ui";

export interface MemberStatementLine {
  date: string;
  line_type: string;
  description: string;
  debit: string;
  credit: string;
  running_balance: string;
}

// Statement lines have no id; DataTable's TData must extend { id: string }.
type MemberStatementRow = MemberStatementLine & { id: string };

const columns: DataTableProps<MemberStatementRow>["columns"] = [
  {
    id: "date",
    accessorKey: "date",
    header: "Date",
    cell: ({ row }) => <FormattedDate value={row.original.date} />,
  },
  { id: "line_type", accessorKey: "line_type", header: "Type" },
  { id: "description", accessorKey: "description", header: "Description" },
  {
    id: "debit",
    accessorKey: "debit",
    header: "Debit",
    cell: ({ row }) => <Money amount={row.original.debit} />,
  },
  {
    id: "credit",
    accessorKey: "credit",
    header: "Credit",
    cell: ({ row }) => <Money amount={row.original.credit} />,
  },
  {
    id: "running_balance",
    accessorKey: "running_balance",
    header: "Balance",
    cell: ({ row }) => <Money amount={row.original.running_balance} />,
  },
];

export function MemberStatementTable({
  rows,
}: {
  rows: MemberStatementLine[];
}) {
  const urlState = useTableUrlState({ defaultPageSize: 100 });
  const withIds = useMemo<MemberStatementRow[]>(
    () => rows.map((r, i) => ({ ...r, id: String(i) })),
    [rows],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return withIds.slice(start, start + urlState.pageSize);
  }, [withIds, urlState.page, urlState.pageSize]);

  return (
    <DataTable<MemberStatementRow>
      id="member-loan-statement"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{
        totalRows: rows.length,
        isError: false,
        isPermissionDenied: false,
      }}
      emptyState={{
        title: "No statement lines yet",
        description: "Statement entries appear here.",
      }}
    />
  );
}
