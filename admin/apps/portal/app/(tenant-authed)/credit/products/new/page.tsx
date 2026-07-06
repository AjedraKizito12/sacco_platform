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
  return <CreateProductForm glAccounts={data ?? []} />;
}
