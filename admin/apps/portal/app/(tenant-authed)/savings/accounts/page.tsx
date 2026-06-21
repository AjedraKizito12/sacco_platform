// admin/apps/portal/app/(tenant-authed)/savings/accounts/page.tsx
import Link from "next/link";
import { Button } from "@sacco/ui";
import type { MemberOut, SavingsAccountOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { AccountsTable, type AccountRow } from "./_components/AccountsTable";

export const metadata = { title: "Savings accounts" };

export default async function SavingsAccountsPage() {
  const { resources } = await getTenantPageContext();
  const [{ data: accounts }, { data: members }] = await Promise.all([
    resources.savings.listAccounts({}) as Promise<{
      data?: SavingsAccountOut[];
      error?: unknown;
    }>,
    resources.members.list({}) as Promise<{ data?: MemberOut[]; error?: unknown }>,
  ]);

  const byId = new Map((members ?? []).map((m) => [m.id, m]));
  const rows: AccountRow[] = (accounts ?? []).map((a) => {
    const m = byId.get(a.member_id);
    return {
      id: a.id,
      member_label: m ? `${m.full_name} (${m.member_number})` : a.member_id,
      product_name: a.product_name,
      interest_rate: a.interest_rate,
      minimum_balance: a.minimum_balance,
    };
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Savings accounts</h1>
        <Button asChild>
          <Link href="/savings/accounts/new">Open account</Link>
        </Button>
      </div>
      <AccountsTable rows={rows} />
    </div>
  );
}
