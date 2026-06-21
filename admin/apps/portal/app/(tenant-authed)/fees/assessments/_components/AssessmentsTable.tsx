// admin/apps/portal/app/(tenant-authed)/fees/assessments/_components/AssessmentsTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  Money,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";

export interface AssessmentRow {
  id: string;
  fee_type_name: string;
  target_type: string;
  amount: string;
  period_start: string;
  status: string;
}

const columns: DataTableProps<AssessmentRow>["columns"] = [
  {
    id: "fee_type_name",
    accessorKey: "fee_type_name",
    header: "Fee type",
    cell: ({ row }) => (
      <Link
        href={`/fees/assessments/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.fee_type_name}
      </Link>
    ),
  },
  { id: "target_type", accessorKey: "target_type", header: "Target" },
  {
    id: "amount",
    accessorKey: "amount",
    header: "Amount",
    cell: ({ row }) => <Money amount={row.original.amount} />,
  },
  {
    id: "period_start",
    accessorKey: "period_start",
    header: "Period",
    cell: ({ row }) => <FormattedDate value={row.original.period_start} />,
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="fee_assessment" status={row.original.status} />,
  },
];

function sortRows(
  rows: AssessmentRow[],
  column: string | null,
  dir: "asc" | "desc",
): AssessmentRow[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof AssessmentRow];
    const bv = b[column as keyof AssessmentRow];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

export function AssessmentsTable({ rows }: { rows: AssessmentRow[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "fee_type_name", direction: "asc" },
    defaultPageSize: 25,
  });

  const sorted = useMemo(
    () => sortRows(rows, urlState.sortColumn, urlState.sortDirection),
    [rows, urlState.sortColumn, urlState.sortDirection],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<AssessmentRow>
      id="fee-assessments"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No assessments yet",
        description: "Create an assessment to charge a fee.",
      }}
    />
  );
}
