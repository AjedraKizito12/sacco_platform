// admin/apps/portal/app/(tenant-authed)/billing/invoices/[id]/page.tsx
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { Button, Card, FormattedDate, Money, StatusBadge } from "@sacco/ui";
import type { InvoiceDetailOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";

export const metadata = { title: "Invoice" };

export default async function TenantInvoiceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();

  const { data } = await (
    resources.billing.myInvoice(id) as Promise<{ data?: InvoiceDetailOut; error?: unknown }>
  );
  if (!data) notFound();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">{data.invoice_number}</h1>
        <Button asChild variant="secondary">
          <a href={`/api/billing/me/invoices/${data.id}/pdf`} target="_blank" rel="noreferrer">
            Download PDF
          </a>
        </Button>
      </div>
      <Card className="flex flex-col gap-3 p-6">
        <Row label="Status" value={<StatusBadge entity="invoice" status={data.status} />} />
        <Row label="Due" value={<FormattedDate value={data.due_at} />} />
        <Row label="Total" value={<Money amount={data.amount_total} currency={data.currency} />} />
        <Row label="Paid" value={<Money amount={data.amount_paid} currency={data.currency} />} />
      </Card>
      <Card className="flex flex-col gap-2 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Line items</h2>
        <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
          {data.line_items.map((li) => (
            <div key={li.id} className="flex justify-between py-2">
              <span className="text-[var(--text-primary)]">
                {li.description}
                {li.quantity > 1 ? ` × ${li.quantity}` : ""}
              </span>
              <Money amount={li.amount} currency={data.currency} />
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-[var(--text-primary)]">{value}</span>
    </div>
  );
}
