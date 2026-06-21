// admin/apps/portal/app/(tenant-authed)/credit/page.tsx
import Link from "next/link";
import { Button } from "@sacco/ui";
import type { LoanProductOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { ProductsTable } from "./_components/ProductsTable";

export const metadata = { title: "Credit" };

export default async function CreditProductsPage() {
  const { resources } = await getTenantPageContext();
  const { data } = await (resources.credit.listProducts({}) as Promise<{
    data?: LoanProductOut[];
    error?: unknown;
  }>);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Loan products</h1>
        <Button asChild>
          <Link href="/credit/products/new">Create product</Link>
        </Button>
      </div>
      <ProductsTable rows={data ?? []} />
    </div>
  );
}
