import { Card, Money, Percentage } from "@sacco/ui";
import { getMemberPageContext } from "@/auth/server-page-context";
import {
  MemberTransactionsTable,
  type MemberTransactionRow,
} from "./_components/MemberTransactionsTable";

export const metadata = { title: "Savings account" };

interface MemberSavingsAccount {
  id: string;
  product_name: string;
  interest_rate: string;
  minimum_balance: string;
  balance: string;
  available_balance: string;
}

export default async function MemberSavingsDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getMemberPageContext();

  const accountsRes = await resources.member.listSavings();
  const accounts = (accountsRes.data ?? []) as MemberSavingsAccount[];
  const account = accounts.find((a) => a.id === id);

  if (!account) {
    return (
      <Card className="p-6">
        <h1 className="text-[var(--text-h4)] font-semibold">
          Account not found
        </h1>
        <p className="mt-2 text-[var(--text-secondary)]">
          This savings account does not exist or is not one of yours.
        </p>
      </Card>
    );
  }

  const txnRes = await resources.member.getSavingsTransactions(id);
  const txns = (txnRes.data ?? []) as MemberTransactionRow[];

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">
        {account.product_name}
      </h1>

      <Card className="flex flex-col gap-3 p-6">
        <div className="flex items-baseline justify-between gap-4">
          <span className="text-[var(--text-secondary)]">
            Available balance
          </span>
          <span className="text-[var(--text-h4)] font-semibold">
            <Money amount={account.available_balance} />
          </span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Total balance</span>
          <Money amount={account.balance} />
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
        <MemberTransactionsTable rows={txns} />
      </div>
    </div>
  );
}
