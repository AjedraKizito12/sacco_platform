// admin/apps/portal/app/(tenant-authed)/shares/accounts/[id]/page.tsx
import { notFound } from "next/navigation";
import { Card, Count, Money } from "@sacco/ui";
import type {
  ShareAccountWithBalanceOut,
  ShareProductOut,
  ShareTransactionOut,
} from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { AccountActions, type GlAccountOption } from "./_components/AccountActions";
import { TransactionsTable } from "./_components/TransactionsTable";

export const metadata = { title: "Share account" };

export default async function ShareAccountDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();
  const { data: account } = await (resources.shares.getAccount(id) as Promise<{
    data?: ShareAccountWithBalanceOut;
    error?: unknown;
  }>);
  if (!account) notFound();

  const [{ data: product }, { data: txns }, { data: glAccounts }] = await Promise.all([
    resources.shares.getProduct(account.share_product_id) as Promise<{
      data?: ShareProductOut;
      error?: unknown;
    }>,
    resources.shares.listTransactions(id) as Promise<{
      data?: ShareTransactionOut[];
      error?: unknown;
    }>,
    resources.ledger.listAccounts({}) as Promise<{
      data?: GlAccountOption[];
      error?: unknown;
    }>,
  ]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">
          {product?.name ?? "Share account"}
        </h1>
        <AccountActions accountId={id} glAccounts={glAccounts ?? []} />
      </div>

      <Card className="flex flex-col gap-3 p-6">
        <div className="flex items-baseline justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Shares held</span>
          <span className="text-[var(--text-h4)] font-semibold">
            <Count value={account.shares_held} />
          </span>
        </div>
        <div className="flex items-baseline justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Total value</span>
          <span className="text-[var(--text-h4)] font-semibold">
            <Money amount={account.total_value} />
          </span>
        </div>
        {product ? (
          <div className="flex justify-between gap-4">
            <span className="text-[var(--text-secondary)]">Par value</span>
            <Money amount={product.par_value} />
          </div>
        ) : null}
      </Card>

      <div className="flex flex-col gap-3">
        <h2 className="text-[var(--text-h5)] font-semibold">Transactions</h2>
        <TransactionsTable rows={txns ?? []} />
      </div>
    </div>
  );
}
