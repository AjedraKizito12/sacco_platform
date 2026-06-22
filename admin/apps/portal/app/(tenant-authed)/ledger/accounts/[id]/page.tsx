// admin/apps/portal/app/(tenant-authed)/ledger/accounts/[id]/page.tsx
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { Card, FormattedDateTime, Money } from "@sacco/ui";
import type { AccountWithBalanceOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";

export const metadata = { title: "Account" };

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}

export default async function LedgerAccountDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();
  const { data: account } = await (resources.ledger.getAccount(id) as Promise<{
    data?: AccountWithBalanceOut;
    error?: unknown;
  }>);
  if (!account) notFound();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">
        {account.code} — {account.name}
      </h1>

      <Card className="flex flex-col gap-3 p-6">
        <div className="flex items-baseline justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Balance</span>
          <span className="text-[var(--text-h4)] font-semibold tabular-nums">
            <Money amount={account.balance} />
          </span>
        </div>
        <Row label="Type">{account.account_type}</Row>
        <Row label="Active">{account.is_active ? "Yes" : "No"}</Row>
        <Row label="Description">{account.description ?? "—"}</Row>
        <Row label="Parent">{account.parent_id ?? "—"}</Row>
        <Row label="Created">
          <FormattedDateTime value={account.created_at} />
        </Row>
      </Card>
    </div>
  );
}
