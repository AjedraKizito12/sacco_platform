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
  return <CreateProductForm glAccounts={data ?? []} />;
}
