// admin/apps/portal/app/(tenant-authed)/reports/fee-collection/page.tsx
import Link from "next/link";
import { Button, Card } from "@sacco/ui";
import type { FeeCollectionReportOut, FeeTypeOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import {
  FeeCollectionFilter,
  type FeeTypeChoice,
} from "./_components/FeeCollectionFilter";
import { FeeCollectionTable } from "./_components/FeeCollectionTable";

export const metadata = { title: "Fee collection" };

export default async function FeeCollectionReportPage({
  searchParams,
}: {
  searchParams: Promise<{ from_date?: string; to_date?: string; fee_type_id?: string }>;
}) {
  const sp = await searchParams;
  const { resources } = await getTenantPageContext();

  const { data: feeTypes } = await (resources.fees.listTypes({}) as Promise<{
    data?: FeeTypeOut[];
    error?: unknown;
  }>);
  const feeTypeChoices: FeeTypeChoice[] = (feeTypes ?? []).map((t) => ({
    id: t.id,
    label: `${t.code} — ${t.name}`,
  }));

  const ready = Boolean(sp.from_date && sp.to_date);
  let data: FeeCollectionReportOut | undefined;
  let error: unknown;
  if (ready) {
    const res = await (resources.reporting.feeCollection({
      from_date: sp.from_date,
      to_date: sp.to_date,
      ...(sp.fee_type_id ? { fee_type_id: sp.fee_type_id } : {}),
    }) as Promise<{ data?: FeeCollectionReportOut; error?: unknown }>);
    data = res.data;
    error = res.error;
  }

  const dl = (format: "pdf" | "csv") =>
    `/api/reporting/fee-collection?${new URLSearchParams({
      format,
      from_date: sp.from_date ?? "",
      to_date: sp.to_date ?? "",
      ...(sp.fee_type_id ? { fee_type_id: sp.fee_type_id } : {}),
    }).toString()}`;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Fee collection</h1>
        {data ? (
          <div className="flex gap-2">
            <Button asChild variant="secondary"><Link href={dl("pdf")} target="_blank" rel="noopener noreferrer">PDF</Link></Button>
            <Button asChild variant="secondary"><Link href={dl("csv")} target="_blank" rel="noopener noreferrer">CSV</Link></Button>
          </div>
        ) : null}
      </div>
      <FeeCollectionFilter feeTypes={feeTypeChoices} />
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
          <FeeCollectionTable rows={data.rows} />
        </>
      )}
    </div>
  );
}
