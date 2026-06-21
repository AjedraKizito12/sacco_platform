// admin/apps/portal/app/(tenant-authed)/reports/savings-statement/page.tsx
import Link from "next/link";
import { Button, Card } from "@sacco/ui";
import type { MemberOut, SavingsStatementOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import {
  SavingsStatementFilter,
  type MemberChoice,
} from "./_components/SavingsStatementFilter";
import { SavingsStatementTable } from "./_components/SavingsStatementTable";

export const metadata = { title: "Savings statement" };

export default async function SavingsStatementReportPage({
  searchParams,
}: {
  searchParams: Promise<{ member_id?: string; from_date?: string; to_date?: string }>;
}) {
  const sp = await searchParams;
  const { resources } = await getTenantPageContext();

  const { data: members } = await (resources.members.list({}) as Promise<{
    data?: MemberOut[];
    error?: unknown;
  }>);
  const memberChoices: MemberChoice[] = (members ?? []).map((m) => ({
    id: m.id,
    label: `${m.full_name} (${m.member_number})`,
  }));

  const ready = Boolean(sp.member_id);
  let data: SavingsStatementOut | undefined;
  let error: unknown;
  if (ready) {
    const res = await (resources.reporting.savingsStatement({
      member_id: sp.member_id,
      ...(sp.from_date ? { from_date: sp.from_date } : {}),
      ...(sp.to_date ? { to_date: sp.to_date } : {}),
    }) as Promise<{ data?: SavingsStatementOut; error?: unknown }>);
    data = res.data;
    error = res.error;
  }

  const dl = (format: "pdf" | "csv") =>
    `/api/reporting/savings-statement?${new URLSearchParams({
      format,
      member_id: sp.member_id ?? "",
      ...(sp.from_date ? { from_date: sp.from_date } : {}),
      ...(sp.to_date ? { to_date: sp.to_date } : {}),
    }).toString()}`;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Savings statement</h1>
        {data ? (
          <div className="flex gap-2">
            <Button asChild variant="secondary"><Link href={dl("pdf")} target="_blank" rel="noopener noreferrer">PDF</Link></Button>
            <Button asChild variant="secondary"><Link href={dl("csv")} target="_blank" rel="noopener noreferrer">CSV</Link></Button>
          </div>
        ) : null}
      </div>
      <SavingsStatementFilter members={memberChoices} />
      {!ready ? (
        <Card className="p-6 text-[var(--text-secondary)]">Choose a member.</Card>
      ) : error || !data ? (
        <Card className="p-6 text-[var(--text-secondary)]">
          No statement available for this member.
        </Card>
      ) : (
        <>
          <p className="text-[var(--text-secondary)]">
            {data.period_start} – {data.period_end}
          </p>
          <SavingsStatementTable rows={data.lines} />
        </>
      )}
    </div>
  );
}
