import { History } from "lucide-react";

export interface AuditBarProps {
  /** Entity table or model name, e.g., "loan", "member". Matches the future
   *  audit-log query API's filter parameter. */
  entityType: string;
  /** Entity primary key (UUID or composite). */
  entityId: string;
}

/**
 * Placeholder for the entity activity panel. Phase 1.7-F (audit-log query
 * API) is still pending; until it ships this component renders a fixed
 * "coming soon" panel with a disabled "View Full History" affordance. The
 * `entityType` / `entityId` props match the future API parameters so
 * feature modules can drop this in today and it lights up when the
 * backend lands.
 */
export function AuditBar({ entityType, entityId }: AuditBarProps) {
  return (
    <section
      aria-label="Activity"
      data-entity-type={entityType}
      data-entity-id={entityId}
      className="rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-4"
    >
      <header className="mb-2 flex items-center gap-2 text-[var(--text-secondary)]">
        <History size={16} strokeWidth={1.75} aria-hidden />
        <h3 className="text-[13px] font-semibold uppercase tracking-wider">
          Activity
        </h3>
      </header>
      <p className="text-[13px] text-[var(--text-tertiary)]">
        Audit history coming soon — the audit-log query endpoint is pending.
      </p>
      <button
        type="button"
        disabled
        className="mt-3 text-[13px] text-[var(--text-tertiary)] underline-offset-2 hover:underline disabled:cursor-not-allowed disabled:opacity-60"
      >
        View Full History
      </button>
    </section>
  );
}
