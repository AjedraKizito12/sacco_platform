// admin/apps/portal/app/(tenant-authed)/credit/products/new/page.tsx
import { getTenantPageContext } from "@/auth/server-page-context";
import { CreateProductForm, type GlAccountOption } from "./_components/CreateProductForm";

export const metadata = { title: "Create loan product" };

export default async function NewLoanProductPage() {
  const { resources } = await getTenantPageContext();
  const { data } = await (resources.ledger.listAccounts({}) as Promise<{
    data?: GlAccountOption[];
    error?: unknown;
  }>);
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Create loan product</h1>
      <CreateProductForm glAccounts={data ?? []} />
    </div>
  );
}
