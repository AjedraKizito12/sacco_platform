// admin/apps/portal/app/(tenant-authed)/ledger/journal-entries/page.tsx
import Link from "next/link";
import { Button } from "@sacco/ui";
import type { JournalEntryOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { JournalEntriesTable } from "./_components/JournalEntriesTable";

export const metadata = { title: "Journal" };

export default async function JournalEntriesPage() {
  const { resources } = await getTenantPageContext();
  const { data } = await (resources.ledger.listJournalEntries({}) as Promise<{
    data?: JournalEntryOut[];
    error?: unknown;
  }>);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Journal</h1>
        <div className="flex gap-2">
          <Button asChild variant="secondary">
            <Link href="/ledger/accounts">Accounts</Link>
          </Button>
          <Button asChild>
            <Link href="/ledger/journal-entries/new">Post GL entry</Link>
          </Button>
        </div>
      </div>
      <JournalEntriesTable rows={data ?? []} />
    </div>
  );
}
