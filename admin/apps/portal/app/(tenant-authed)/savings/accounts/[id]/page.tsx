// admin/apps/portal/app/(tenant-authed)/savings/accounts/[id]/page.tsx
import { notFound } from "next/navigation";
import { Card, Money, Percentage } from "@sacco/ui";
import type {
  SavingsAccountWithBalanceOut,
  SavingsTransactionOut,
} from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { AccountActions, type GlAccountOption } from "./_components/AccountActions";
import { TransactionsTable } from "./_components/TransactionsTable";

export const metadata = { title: "Savings account" };

export default async function SavingsAccountDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();
  const [{ data: account }, { data: txns }, { data: glAccounts }] = await Promise.all([
    resources.savings.getAccount(id) as Promise<{
      data?: SavingsAccountWithBalanceOut;
      error?: unknown;
    }>,
    resources.savings.listTransactions(id) as Promise<{
      data?: SavingsTransactionOut[];
      error?: unknown;
    }>,
    resources.ledger.listAccounts({}) as Promise<{
      data?: GlAccountOption[];
      error?: unknown;
    }>,
  ]);
  if (!account) notFound();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">{account.product_name}</h1>
        <AccountActions accountId={id} glAccounts={glAccounts ?? []} />
      </div>

      <Card className="flex flex-col gap-3 p-6">
        <div className="flex items-baseline justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Balance</span>
          <span className="text-[var(--text-h4)] font-semibold">
            <Money amount={account.balance} />
          </span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Product</span>
          <span>{account.product_name}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Interest</span>
          <Percentage value={account.interest_rate} />
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Minimum balance</span>
          <Money amount={account.minimum_balance} />
        </div>
      </Card>

      <div className="flex flex-col gap-3">
        <h2 className="text-[var(--text-h5)] font-semibold">Transactions</h2>
        <TransactionsTable rows={txns ?? []} />
      </div>
    </div>
  );
}
