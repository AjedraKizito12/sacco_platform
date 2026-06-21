// admin/apps/portal/app/(tenant-authed)/reports/income-statement/page.tsx
import Link from "next/link";
import { Button, Card } from "@sacco/ui";
import type { IncomeStatementOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { DateRangeFilter } from "./_components/DateRangeFilter";
import { IncomeStatementTable } from "./_components/IncomeStatementTable";

export const metadata = { title: "Income statement" };

export default async function IncomeStatementReportPage({
  searchParams,
}: {
  searchParams: Promise<{ from_date?: string; to_date?: string }>;
}) {
  const sp = await searchParams;
  const ready = Boolean(sp.from_date && sp.to_date);
  const { resources } = await getTenantPageContext();

  let data: IncomeStatementOut | undefined;
  let error: unknown;
  if (ready) {
    const res = await (resources.reporting.incomeStatement({
      from_date: sp.from_date,
      to_date: sp.to_date,
    }) as Promise<{ data?: IncomeStatementOut; error?: unknown }>);
    data = res.data;
    error = res.error;
  }

  const dl = (format: "pdf" | "csv") =>
    `/api/reporting/income-statement?${new URLSearchParams({
      format,
      from_date: sp.from_date ?? "",
      to_date: sp.to_date ?? "",
    }).toString()}`;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Income statement</h1>
        {data ? (
          <div className="flex gap-2">
            <Button asChild variant="secondary"><Link href={dl("pdf")} target="_blank" rel="noopener noreferrer">PDF</Link></Button>
            <Button asChild variant="secondary"><Link href={dl("csv")} target="_blank" rel="noopener noreferrer">CSV</Link></Button>
          </div>
        ) : null}
      </div>
      <DateRangeFilter basePath="/reports/income-statement" />
      {!ready ? (
        <Card className="p-6 text-[var(--text-secondary)]">Choose a from and to date.</Card>
      ) : error || !data ? (
        <Card className="p-6 text-[var(--text-secondary)]">
          No report available for this period.
        </Card>
      ) : (
        <>
          <p className="text-[var(--text-secondary)]">
            {data.period_start} – {data.period_end}
          </p>
          <IncomeStatementTable rows={data.lines} />
        </>
      )}
    </div>
  );
}
