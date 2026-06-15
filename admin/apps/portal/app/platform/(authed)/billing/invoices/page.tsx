// admin/apps/portal/app/platform/(authed)/billing/invoices/page.tsx
import { Card } from "@sacco/ui";
import type { InvoiceOut, TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { BillingTabs } from "../_components/BillingTabs";
import { InvoicesTable, type InvoiceRow } from "./_components/InvoicesTable";

export const metadata = { title: "Invoices" };

export default async function BillingInvoicesPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.read");

  const [{ data: invoices }, { data: tenants }] = await Promise.all([
    resources.billing.listInvoices() as Promise<{ data?: InvoiceOut[]; error?: unknown }>,
    resources.tenants.list() as Promise<{ data?: TenantOut[]; error?: unknown }>,
  ]);

  const tenantName = new Map((tenants ?? []).map((t) => [t.id, t.name]));
  const rows: InvoiceRow[] = (invoices ?? []).map((inv) => ({
    id: inv.id,
    invoice_number: inv.invoice_number,
    tenant_id: inv.tenant_id,
    tenant_name: tenantName.get(inv.tenant_id) ?? inv.tenant_id,
    amount_total: inv.amount_total,
    amount_paid: inv.amount_paid,
    currency: inv.currency,
    status: inv.status,
    due_at: inv.due_at,
  }));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Billing</h1>
      <BillingTabs />
      <Card className="p-0">
        <InvoicesTable rows={rows} />
      </Card>
    </div>
  );
}
