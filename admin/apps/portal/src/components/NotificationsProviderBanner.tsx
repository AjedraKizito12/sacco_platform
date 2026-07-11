import { Info } from "lucide-react";

/**
 * Fixed copy (SaaS roadmap Phase 3): shown on notification admin/settings
 * pages until a real email/SMS provider ships.
 */
export function NotificationsProviderBanner() {
  return (
    <div
      role="status"
      className="flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--border-subtle)] bg-[var(--status-info-bg)] px-4 py-3 text-sm text-[var(--text-primary)]"
    >
      <Info size={16} strokeWidth={1.75} aria-hidden />
      Notifications: provider=null — real delivery disabled
    </div>
  );
}
