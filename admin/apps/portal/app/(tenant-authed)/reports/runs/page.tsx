// admin/apps/portal/app/(tenant-authed)/reports/runs/page.tsx
import type { ReportRunOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { RunsTable } from "./_components/RunsTable";

export const metadata = { title: "Report runs" };

export default async function ReportRunsPage() {
  const { resources } = await getTenantPageContext();
  const { data } = await (resources.reporting.listRuns({}) as Promise<{
    data?: ReportRunOut[];
    error?: unknown;
  }>);
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Report runs</h1>
      <RunsTable rows={data ?? []} />
    </div>
  );
}
