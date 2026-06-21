// admin/apps/portal/app/(tenant-authed)/shares/accounts/page.tsx
import Link from "next/link";
import { Button } from "@sacco/ui";
import type { MemberOut, ShareAccountListItemOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { AccountsTable, type AccountRow } from "./_components/AccountsTable";

export const metadata = { title: "Share accounts" };

export default async function ShareAccountsPage() {
  const { resources } = await getTenantPageContext();
  const [{ data: accounts }, { data: members }] = await Promise.all([
    resources.shares.listAccounts({}) as Promise<{
      data?: ShareAccountListItemOut[];
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
      shares_held: a.shares_held,
      total_value: a.total_value,
    };
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Share accounts</h1>
        <Button asChild>
          <Link href="/shares/accounts/new">Open account</Link>
        </Button>
      </div>
      <AccountsTable rows={rows} />
    </div>
  );
}
