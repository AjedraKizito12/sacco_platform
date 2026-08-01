"use client";

import { RelativeTime } from "@sacco/ui";
import { BACKUP_STALE_HOURS, VERIFY_STALE_DAYS, isStale } from "@sacco/schemas";

function Tile({
  label,
  at,
  stale,
  hint,
}: {
  label: string;
  at: string | null;
  stale: boolean;
  hint: string;
}) {
  return (
    <div
      data-testid={stale ? "tile-stale" : "tile-fresh"}
      className={`flex flex-col gap-1 rounded-[var(--radius-lg)] border border-[var(--border-subtle)] p-4 ${
        stale
          ? "bg-[var(--status-danger-bg)]"
          : "bg-[var(--status-success-bg)]"
      }`}
    >
      <span className="text-[13px] text-[var(--text-secondary)]">{label}</span>
      <span className="text-[var(--text-h5)] font-semibold">
        {at ? <RelativeTime value={at} /> : "Never"}
      </span>
      <span className="text-[12px] text-[var(--text-tertiary)]">
        {stale ? `Stale — ${hint}` : "Fresh"}
      </span>
    </div>
  );
}

/**
 * Two at-a-glance freshness tiles. Staleness is computed with the shared
 * `isStale` helper against the roadmap thresholds; a null timestamp is always
 * stale (and renders "Never"). Presentational — the server page passes the
 * authoritative timestamps in.
 */
export function BackupFreshnessTiles({
  lastBackupAt,
  lastVerifiedAt,
  now,
}: {
  lastBackupAt: string | null;
  lastVerifiedAt: string | null;
  now?: number;
}) {
  const backupStale = isStale(lastBackupAt, BACKUP_STALE_HOURS * 3600_000, now);
  const verifyStale = isStale(lastVerifiedAt, VERIFY_STALE_DAYS * 86400_000, now);

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <Tile
        label={`Last successful backup (stale after ${BACKUP_STALE_HOURS}h)`}
        at={lastBackupAt}
        stale={backupStale}
        hint={`no successful backup in the last ${BACKUP_STALE_HOURS}h`}
      />
      <Tile
        label={`Last verified restore (stale after ${VERIFY_STALE_DAYS}d)`}
        at={lastVerifiedAt}
        stale={verifyStale}
        hint={`no passing drill in the last ${VERIFY_STALE_DAYS} days`}
      />
    </div>
  );
}
