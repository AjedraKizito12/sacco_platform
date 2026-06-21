// admin/apps/portal/app/(tenant-authed)/reports/loan-portfolio/_components/LoanPortfolioTable.tsx
"use client";

import { useMemo } from "react";
import {
  Count,
  DataTable,
  type DataTableProps,
  Money,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import type { LoanPortfolioRowOut } from "@sacco/schemas";

type Row = LoanPortfolioRowOut & { id: string };

const columns: DataTableProps<Row>["columns"] = [
  { id: "loan_reference", accessorKey: "loan_reference", header: "Loan ref" },
  { id: "product_name", accessorKey: "product_name", header: "Product" },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="loan" status={row.original.status} />,
  },
  {
    id: "outstanding_principal",
    accessorKey: "outstanding_principal",
    header: "Outstanding",
    cell: ({ row }) => <Money amount={row.original.outstanding_principal} />,
  },
  {
    id: "accrued_interest",
    accessorKey: "accrued_interest",
    header: "Accrued interest",
    cell: ({ row }) => <Money amount={row.original.accrued_interest} />,
  },
  {
    id: "days_in_arrears",
    accessorKey: "days_in_arrears",
    header: "Days in arrears",
    cell: ({ row }) => <Count value={row.original.days_in_arrears} />,
  },
  { id: "aging_bucket", accessorKey: "aging_bucket", header: "Aging" },
];

export function LoanPortfolioTable({ rows }: { rows: LoanPortfolioRowOut[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 100 });
  const withIds = useMemo<Row[]>(() => rows.map((r) => ({ ...r, id: r.loan_id })), [rows]);
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return withIds.slice(start, start + urlState.pageSize);
  }, [withIds, urlState.page, urlState.pageSize]);

  return (
    <DataTable<Row>
      id="loan-portfolio"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No loans in the portfolio",
        description: "No data for the selected date.",
      }}
    />
  );
}
