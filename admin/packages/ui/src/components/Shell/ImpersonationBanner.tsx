"use client";

import { Button } from "../Button";
import { FormattedDateTime } from "../FormattedDate";

export interface ImpersonationBannerProps {
  tenantName: string;
  /** ISO timestamp when the impersonation session auto-expires. */
  expiresAt: string;
  onEnd(): void;
  busy?: boolean;
}

/**
 * Persistent, high-visibility banner shown at the top of the tenant shell
 * while a platform operator is impersonating a tenant. The session also
 * expires server-side at `expiresAt`; "End now" terminates it early.
 */
export function ImpersonationBanner({
  tenantName,
  expiresAt,
  onEnd,
  busy = false,
}: ImpersonationBannerProps) {
  return (
    <div
      role="status"
      className="flex items-center justify-between gap-4 bg-[var(--status-warning-bg)] px-6 py-2 text-[13px] text-[var(--text-warning)]"
    >
      <span>
        <strong className="font-semibold">Impersonating {tenantName}</strong>
        {" · ends "}
        <FormattedDateTime value={expiresAt} />
      </span>
      <Button variant="secondary" size="sm" onClick={onEnd} disabled={busy}>
        End now
      </Button>
    </div>
  );
}
