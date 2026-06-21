// admin/apps/portal/app/(tenant-authed)/fees/types/page.tsx
import Link from "next/link";
import { Button } from "@sacco/ui";
import type { FeeTypeOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { FeeTypesTable } from "./_components/FeeTypesTable";

export const metadata = { title: "Fees" };

export default async function FeeTypesPage() {
  const { resources } = await getTenantPageContext();
  const { data } = await (resources.fees.listTypes({}) as Promise<{
    data?: FeeTypeOut[];
    error?: unknown;
  }>);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Fee types</h1>
        <div className="flex gap-2">
          <Button asChild variant="secondary">
            <Link href="/fees/assessments">Assessments</Link>
          </Button>
          <Button asChild>
            <Link href="/fees/types/new">Create fee type</Link>
          </Button>
        </div>
      </div>
      <FeeTypesTable rows={data ?? []} />
    </div>
  );
}
