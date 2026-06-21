// admin/apps/portal/app/(tenant-authed)/fees/types/new/page.tsx
import { getTenantPageContext } from "@/auth/server-page-context";
import { CreateFeeTypeForm, type GlAccountOption } from "./_components/CreateFeeTypeForm";

export const metadata = { title: "Create fee type" };

export default async function NewFeeTypePage() {
  const { resources } = await getTenantPageContext();
  const { data } = await (resources.ledger.listAccounts({}) as Promise<{
    data?: GlAccountOption[];
    error?: unknown;
  }>);
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Create fee type</h1>
      <CreateFeeTypeForm glAccounts={data ?? []} />
    </div>
  );
}
