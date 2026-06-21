// admin/apps/portal/app/(tenant-authed)/savings/page.tsx
import Link from "next/link";
import { Button } from "@sacco/ui";
import type { SavingsProductOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { ProductsTable } from "./_components/ProductsTable";

export const metadata = { title: "Savings" };

export default async function SavingsPage() {
  const { resources } = await getTenantPageContext();
  const { data } = await (resources.savings.listProducts({}) as Promise<{
    data?: SavingsProductOut[];
    error?: unknown;
  }>);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Savings products</h1>
        <div className="flex gap-2">
          <Button asChild variant="secondary">
            <Link href="/savings/accounts">Accounts</Link>
          </Button>
          <Button asChild>
            <Link href="/savings/products/new">Create product</Link>
          </Button>
        </div>
      </div>
      <ProductsTable rows={data ?? []} />
    </div>
  );
}
