// Mirrors app/platform_/ops/schemas.py (backup/restore operational telemetry).
// Timestamps are ISO-8601 strings; sizes/lag are integers or null.
export interface BackupRunOut {
  id: string;
  backup_type: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  repo_size_bytes: number | null;
  wal_lag_seconds: number | null;
  detail: string | null;
  created_at: string;
}

export interface BackupVerificationOut {
  id: string;
  requested_by: string | null;
  status: string;
  detail: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface BackupStatusOut {
  recent_runs: BackupRunOut[];
  latest_verification: BackupVerificationOut | null;
}

export interface LastVerifiedOut {
  last_verified_at: string | null;
}

// Freshness thresholds (roadmap): a base backup older than 24h, or a verified
// restore older than 7 days, reads as stale in the portal widget.
export const BACKUP_STALE_HOURS = 24;
export const VERIFY_STALE_DAYS = 7;

/** True when `iso` is null or older than `maxAgeMs` relative to `now`. */
export function isStale(iso: string | null, maxAgeMs: number, now = Date.now()): boolean {
  if (iso === null) return true;
  return now - Date.parse(iso) > maxAgeMs;
}
