// admin/apps/portal/app/platform/(authed)/billing/invoices/_components/InvoicesTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  FormattedDate,
  Money,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";

export interface InvoiceRow {
  id: string;
  invoice_number: string;
  tenant_id: string;
  tenant_name: string;
  amount_total: string;
  amount_paid: string;
  currency: string;
  status: string;
  due_at: string;
}

const STATUS_FILTER_OPTIONS = [
  "draft",
  "issued",
  "partial",
  "paid",
  "overdue",
  "void",
] as const;

const columns: DataTableProps<InvoiceRow>["columns"] = [
  {
    id: "invoice_number",
    accessorKey: "invoice_number",
    header: "Invoice",
    cell: ({ row }) => (
      <Link
        href={`/platform/billing/invoices/${row.original.id}`}
        className="font-medium text-[var(--text-link)] hover:underline"
      >
        {row.original.invoice_number}
      </Link>
    ),
  },
  { id: "tenant_name", accessorKey: "tenant_name", header: "Tenant" },
  {
    id: "amount_total",
    accessorKey: "amount_total",
    header: "Total",
    cell: ({ row }) => <Money amount={row.original.amount_total} currency={row.original.currency} />,
  },
  {
    id: "amount_paid",
    accessorKey: "amount_paid",
    header: "Paid",
    cell: ({ row }) => <Money amount={row.original.amount_paid} currency={row.original.currency} />,
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

export function filterInvoices(rows: InvoiceRow[], status: string | undefined): InvoiceRow[] {
  if (!status) return rows;
  return rows.filter((r) => r.status === status);
}

export function sortInvoices(
  rows: InvoiceRow[],
  column: string | null,
  dir: "asc" | "desc",
): InvoiceRow[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof InvoiceRow];
    const bv = b[column as keyof InvoiceRow];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

/** Full (unpaginated) invoice list through DataTable; client-side filter/sort/paginate. */
export function InvoicesTable({ rows }: { rows: InvoiceRow[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "invoice_number", direction: "desc" },
    defaultPageSize: 25,
    filterKeys: ["status"],
  });

  const filtered = useMemo(
    () => filterInvoices(rows, urlState.filters["status"]),
    [rows, urlState.filters],
  );
  const sorted = useMemo(
    () => sortInvoices(filtered, urlState.sortColumn, urlState.sortDirection),
    [filtered, urlState.sortColumn, urlState.sortDirection],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<InvoiceRow>
      id="billing-invoices"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: filtered.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No invoices",
        description: "Invoices are generated automatically from active subscriptions.",
      }}
      filterSlot={
        <Select
          value={urlState.filters["status"] ?? "all"}
          onValueChange={(v) => urlState.setFilter("status", v === "all" ? null : v)}
        >
          <SelectTrigger className="w-44" aria-label="Filter by status">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {STATUS_FILTER_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    />
  );
}
