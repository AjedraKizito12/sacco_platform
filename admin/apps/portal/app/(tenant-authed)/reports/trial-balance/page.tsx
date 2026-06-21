// admin/apps/portal/app/(tenant-authed)/reports/trial-balance/page.tsx
import Link from "next/link";
import { Button, Card } from "@sacco/ui";
import type { TrialBalanceOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { AsOfFilter } from "./_components/AsOfFilter";
import { TrialBalanceTable } from "./_components/TrialBalanceTable";

export const metadata = { title: "Trial balance" };

export default async function TrialBalanceReportPage({
  searchParams,
}: {
  searchParams: Promise<{ as_of?: string }>;
}) {
  const sp = await searchParams;
  const { resources } = await getTenantPageContext();
  const { data, error } = await (resources.reporting.trialBalance(
    sp.as_of ? { as_of: sp.as_of } : {},
  ) as Promise<{ data?: TrialBalanceOut; error?: unknown }>);

  const dl = (format: "pdf" | "csv") =>
    `/api/reporting/trial-balance?format=${format}${sp.as_of ? `&as_of=${sp.as_of}` : ""}`;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Trial balance</h1>
        {data ? (
          <div className="flex gap-2">
            <Button asChild variant="secondary"><Link href={dl("pdf")} target="_blank" rel="noopener noreferrer">PDF</Link></Button>
            <Button asChild variant="secondary"><Link href={dl("csv")} target="_blank" rel="noopener noreferrer">CSV</Link></Button>
          </div>
        ) : null}
      </div>
      <AsOfFilter basePath="/reports/trial-balance" />
      {error || !data ? (
        <Card className="p-6 text-[var(--text-secondary)]">
          No report available for this date.
        </Card>
      ) : (
        <>
          <p className="text-[var(--text-secondary)]">As of {data.as_of_date}</p>
          <TrialBalanceTable rows={data.lines} />
        </>
      )}
    </div>
  );
}
