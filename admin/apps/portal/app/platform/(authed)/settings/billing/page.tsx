import type { ReactNode } from "react";
import Link from "next/link";
import { Card } from "@sacco/ui";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";

export const metadata = { title: "Billing settings" };

function Row({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[var(--text-h5)] font-semibold">{title}</span>
      <span className="text-[13px] text-[var(--text-secondary)]">{children}</span>
    </div>
  );
}

export default async function BillingSettingsPage() {
  const { user } = await getPlatformPageContext();
  requirePlatformPermission(user, "settings.read");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Billing settings</h1>
      <Card className="flex flex-col gap-5 p-6">
        <Row title="Invoice numbering">
          Invoices are numbered <span className="font-mono">INV-YYYY-NNNNNN</span> per year.
        </Row>
        <Row title="Plans &amp; default pricing">
          Plans are managed in the billing area, and assigned per tenant on the tenant
          detail page.{" "}
          <Link href="/platform/billing/plans" className="text-[var(--text-link)]">
            Manage plans
          </Link>
        </Row>
        <Row title="Grace period">
          Past-due subscriptions retain access through their grace period before suspension.
        </Row>
      </Card>
    </div>
  );
}
