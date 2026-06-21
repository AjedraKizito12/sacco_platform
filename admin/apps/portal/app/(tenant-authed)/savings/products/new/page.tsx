// admin/apps/portal/app/(tenant-authed)/savings/products/new/page.tsx
import { getTenantPageContext } from "@/auth/server-page-context";
import { CreateProductForm, type GlAccountOption } from "./_components/CreateProductForm";

export const metadata = { title: "Create savings product" };

export default async function NewSavingsProductPage() {
  const { resources } = await getTenantPageContext();
  const { data } = await (resources.ledger.listAccounts({}) as Promise<{
    data?: GlAccountOption[];
    error?: unknown;
  }>);
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Create savings product</h1>
      <CreateProductForm glAccounts={data ?? []} />
    </div>
  );
}
