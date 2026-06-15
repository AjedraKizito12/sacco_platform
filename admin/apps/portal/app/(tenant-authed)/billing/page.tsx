// admin/apps/portal/app/(tenant-authed)/billing/page.tsx
import { Card, FormattedDate, StatusBadge } from "@sacco/ui";
import type { InvoiceOut, SubscriptionOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { TenantInvoicesTable, type TenantInvoiceRow } from "./_components/TenantInvoicesTable";

export const metadata = { title: "Billing" };

export default async function TenantBillingPage() {
  const { resources } = await getTenantPageContext();

  const [{ data: sub }, { data: invoices }] = await Promise.all([
    resources.billing.mySubscription() as Promise<{ data?: SubscriptionOut; error?: unknown }>,
    resources.billing.myInvoices() as Promise<{ data?: InvoiceOut[]; error?: unknown }>,
  ]);

  const rows: TenantInvoiceRow[] = (invoices ?? []).map((inv) => ({
    id: inv.id,
    invoice_number: inv.invoice_number,
    amount_total: inv.amount_total,
    currency: inv.currency,
    status: inv.status,
    due_at: inv.due_at,
  }));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Billing</h1>
      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Subscription</h2>
        {sub ? (
          <>
            <div className="flex justify-between gap-4">
              <span className="text-[var(--text-secondary)]">Status</span>
              <StatusBadge entity="subscription" status={sub.status} />
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-[var(--text-secondary)]">Current period ends</span>
              <FormattedDate value={sub.current_period_end} />
            </div>
          </>
        ) : (
          <p className="text-[var(--text-secondary)]">No active subscription.</p>
        )}
      </Card>
      <Card className="p-0">
        <TenantInvoicesTable rows={rows} />
      </Card>
    </div>
  );
}
