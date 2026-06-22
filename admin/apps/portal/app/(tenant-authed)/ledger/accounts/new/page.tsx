// admin/apps/portal/app/(tenant-authed)/ledger/accounts/new/page.tsx
import { getTenantPageContext } from "@/auth/server-page-context";
import { CreateAccountForm, type AccountOption } from "./_components/CreateAccountForm";

export const metadata = { title: "Create account" };

export default async function NewLedgerAccountPage() {
  const { resources } = await getTenantPageContext();
  const { data } = await (resources.ledger.listAccounts({}) as Promise<{
    data?: AccountOption[];
    error?: unknown;
  }>);
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Create account</h1>
      <CreateAccountForm parents={data ?? []} />
    </div>
  );
}
