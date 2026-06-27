"use client";

import { useMemo } from "react";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  Money,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";

export interface MemberFeeRow {
  id: string;
  amount: string;
  status: string;
  assessed_at?: string;
  period_start?: string;
}

const columns: DataTableProps<MemberFeeRow>["columns"] = [
  {
    id: "amount",
    accessorKey: "amount",
    header: "Amount",
    cell: ({ row }) => <Money amount={row.original.amount} />,
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge entity="fee_assessment" status={row.original.status} />
    ),
  },
  {
    id: "period_start",
    accessorKey: "period_start",
    header: "Period",
    cell: ({ row }) =>
      row.original.period_start ? (
        <FormattedDate value={row.original.period_start} />
      ) : (
        "—"
      ),
  },
  {
    id: "assessed_at",
    accessorKey: "assessed_at",
    header: "Assessed on",
    cell: ({ row }) =>
      row.original.assessed_at ? (
        <FormattedDate value={row.original.assessed_at} />
      ) : (
        "—"
      ),
  },
];

export function MemberFeesTable({ rows }: { rows: MemberFeeRow[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 25 });
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<MemberFeeRow>
      id="member-fees"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{
        totalRows: rows.length,
        isError: false,
        isPermissionDenied: false,
      }}
      emptyState={{
        title: "No fees",
        description: "Your fee assessments will appear here.",
      }}
    />
  );
}
