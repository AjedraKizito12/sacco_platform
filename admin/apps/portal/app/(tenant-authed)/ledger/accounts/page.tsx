// admin/apps/portal/app/(tenant-authed)/ledger/accounts/page.tsx
import Link from "next/link";
import { Button } from "@sacco/ui";
import type { AccountOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { AccountsTable } from "./_components/AccountsTable";

export const metadata = { title: "Ledger" };

export default async function LedgerAccountsPage() {
  const { resources } = await getTenantPageContext();
  const { data } = await (resources.ledger.listAccounts({}) as Promise<{
    data?: AccountOut[];
    error?: unknown;
  }>);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Chart of accounts</h1>
        <div className="flex gap-2">
          <Button asChild variant="secondary">
            <Link href="/ledger/journal-entries">Journal</Link>
          </Button>
          <Button asChild>
            <Link href="/ledger/accounts/new">Create account</Link>
          </Button>
        </div>
      </div>
      <AccountsTable rows={data ?? []} />
    </div>
  );
}
