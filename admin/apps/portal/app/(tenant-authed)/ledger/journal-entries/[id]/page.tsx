// admin/apps/portal/app/(tenant-authed)/ledger/journal-entries/[id]/page.tsx
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { Card, FormattedDateTime } from "@sacco/ui";
import type { JournalEntryOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { LinesTable } from "./_components/LinesTable";

export const metadata = { title: "Journal entry" };

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}

export default async function JournalEntryDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();
  const { data: entry } = await (resources.ledger.getJournalEntry(id) as Promise<{
    data?: JournalEntryOut;
    error?: unknown;
  }>);
  if (!entry) notFound();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">{entry.reference}</h1>

      <Card className="flex flex-col gap-3 p-6">
        <Row label="Description">{entry.description}</Row>
        <Row label="Posted">
          <FormattedDateTime value={entry.posted_at} />
        </Row>
      </Card>

      <h2 className="text-[var(--text-h5)] font-semibold">Lines</h2>
      <LinesTable rows={entry.lines} />
    </div>
  );
}
