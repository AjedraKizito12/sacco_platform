// admin/apps/portal/app/(tenant-authed)/billing/_components/TenantInvoicesTable.tsx
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

export interface TenantInvoiceRow {
  id: string;
  invoice_number: string;
  amount_total: string;
  currency: string;
  status: string;
  due_at: string;
}

const columns: DataTableProps<TenantInvoiceRow>["columns"] = [
  {
    id: "invoice_number",
    accessorKey: "invoice_number",
    header: "Invoice",
    cell: ({ row }) => (
      <Link
        href={`/billing/invoices/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.invoice_number}
      </Link>
    ),
  },
  {
    id: "amount_total",
    accessorKey: "amount_total",
    header: "Total",
    cell: ({ row }) => <Money amount={row.original.amount_total} currency={row.original.currency} />,
  },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge entity="invoice" status={row.original.status} />,
  },
  {
    id: "due_at",
    accessorKey: "due_at",
    header: "Due",
    cell: ({ row }) => <FormattedDate value={row.original.due_at} />,
  },
];

export function TenantInvoicesTable({ rows }: { rows: TenantInvoiceRow[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "invoice_number", direction: "desc" },
    defaultPageSize: 25,
  });
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<TenantInvoiceRow>
      id="tenant-invoices"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{ title: "No invoices", description: "Your invoices will appear here." }}
    />
  );
}
