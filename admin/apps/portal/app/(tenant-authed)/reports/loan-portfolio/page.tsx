// admin/apps/portal/app/(tenant-authed)/reports/loan-portfolio/page.tsx
import Link from "next/link";
import { Button, Card } from "@sacco/ui";
import type { LoanPortfolioOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { LoanPortfolioFilter } from "./_components/LoanPortfolioFilter";
import { LoanPortfolioTable } from "./_components/LoanPortfolioTable";

export const metadata = { title: "Loan portfolio" };

export default async function LoanPortfolioReportPage({
  searchParams,
}: {
  searchParams: Promise<{ as_of?: string; status?: string }>;
}) {
  const sp = await searchParams;
  const { resources } = await getTenantPageContext();
  const query: Record<string, string> = {
    ...(sp.as_of ? { as_of: sp.as_of } : {}),
    ...(sp.status ? { status: sp.status } : {}),
  };
  const { data, error } = await (resources.reporting.loanPortfolio(query) as Promise<{
    data?: LoanPortfolioOut;
    error?: unknown;
  }>);

  const dl = (format: "pdf" | "csv") =>
    `/api/reporting/loan-portfolio?${new URLSearchParams({ format, ...query }).toString()}`;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Loan portfolio</h1>
        {data ? (
          <div className="flex gap-2">
            <Button asChild variant="secondary"><Link href={dl("pdf")} target="_blank" rel="noopener noreferrer">PDF</Link></Button>
            <Button asChild variant="secondary"><Link href={dl("csv")} target="_blank" rel="noopener noreferrer">CSV</Link></Button>
          </div>
        ) : null}
      </div>
      <LoanPortfolioFilter basePath="/reports/loan-portfolio" />
      {error || !data ? (
        <Card className="p-6 text-[var(--text-secondary)]">
          No report available for this date.
        </Card>
      ) : (
        <>
          <p className="text-[var(--text-secondary)]">As of {data.as_of_date}</p>
          <LoanPortfolioTable rows={data.rows} />
        </>
      )}
    </div>
  );
}
