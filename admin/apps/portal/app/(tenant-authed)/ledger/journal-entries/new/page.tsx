// admin/apps/portal/app/(tenant-authed)/ledger/journal-entries/new/page.tsx
import { getTenantPageContext } from "@/auth/server-page-context";
import { ManualGLForm, type AccountOption } from "./_components/ManualGLForm";

export const metadata = { title: "Post GL entry" };

export default async function NewJournalEntryPage() {
  const { resources } = await getTenantPageContext();
  const { data } = await (resources.ledger.listAccounts({}) as Promise<{
    data?: AccountOption[];
    error?: unknown;
  }>);
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Post manual GL entry</h1>
      <ManualGLForm accounts={data ?? []} />
    </div>
  );
}
