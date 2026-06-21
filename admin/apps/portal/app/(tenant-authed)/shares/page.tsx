// admin/apps/portal/app/(tenant-authed)/shares/page.tsx
import Link from "next/link";
import { Button } from "@sacco/ui";
import type { ShareProductOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { ProductsTable } from "./_components/ProductsTable";

export const metadata = { title: "Shares" };

export default async function SharesPage() {
  const { resources } = await getTenantPageContext();
  const { data } = await (resources.shares.listProducts({}) as Promise<{
    data?: ShareProductOut[];
    error?: unknown;
  }>);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Share products</h1>
        <div className="flex gap-2">
          <Button asChild variant="secondary">
            <Link href="/shares/accounts">Accounts</Link>
          </Button>
          <Button asChild>
            <Link href="/shares/products/new">Create product</Link>
          </Button>
        </div>
      </div>
      <ProductsTable rows={data ?? []} />
    </div>
  );
}
