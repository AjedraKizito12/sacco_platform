import { Card, TrendAreaChart, type TrendPoint } from "@sacco/ui";
import type { BackupStatusOut, LastVerifiedOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { BackupFreshnessTiles } from "./_components/BackupFreshnessTiles";
import { BackupRunsTable } from "./_components/BackupRunsTable";
import { VerifyNowButton } from "./_components/VerifyNowButton";

export const metadata = { title: "Backups" };

export default async function BackupsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "operations.read");

  const [backupsRes, verifiedRes] = await Promise.all([
    resources.ops.getBackups() as Promise<{
      data?: BackupStatusOut;
      error?: unknown;
    }>,
    resources.ops.lastVerifiedAt() as Promise<{
      data?: LastVerifiedOut;
      error?: unknown;
    }>,
  ]);
  const data = backupsRes.data;

  const header = (
    <div className="flex items-center justify-between">
      <h1 className="text-[var(--text-h3)] font-semibold">Backups</h1>
      <VerifyNowButton />
    </div>
  );

  if (!data) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <Card className="p-6 text-[var(--text-secondary)]">
          Couldn&apos;t load backup status. Viewing backup operations requires
          platform superuser access.
        </Card>
      </div>
    );
  }

  const runs = data.recent_runs;
  const lastBackupAt =
    runs.find((r) => r.status === "succeeded")?.finished_at ?? null;
  const lastVerifiedAt = verifiedRes.data?.last_verified_at ?? null;

  // Repo size over recent successful runs, oldest → newest for the trend.
  const trend: TrendPoint[] = runs
    .filter((r) => r.repo_size_bytes !== null)
    .slice()
    .reverse()
    .map((r) => ({
      label: (r.finished_at ?? r.created_at).slice(0, 10),
      value: r.repo_size_bytes as number,
    }));

  return (
    <div className="flex flex-col gap-6">
      {header}

      <BackupFreshnessTiles
        lastBackupAt={lastBackupAt}
        lastVerifiedAt={lastVerifiedAt}
      />

      {trend.length >= 2 ? (
        <Card className="flex flex-col gap-3 p-6">
          <h2 className="text-[var(--text-h5)] font-semibold">
            Repository size trend
          </h2>
          <TrendAreaChart
            data={trend}
            ariaLabel="Backup repository size over recent runs"
          />
        </Card>
      ) : null}

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">
          Recent backup runs
        </h2>
        <BackupRunsTable rows={runs} />
      </Card>
    </div>
  );
}
