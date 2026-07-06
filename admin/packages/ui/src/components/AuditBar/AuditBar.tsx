import { History } from "lucide-react";

export interface AuditBarEntry {
  id: string;
  operation: string;
  actorLabel: string | null;
  occurredAt: string;
}

export interface AuditBarProps {
  /** Entity table or model name, e.g., "loan", "member". Matches the
   *  audit-log query API's filter parameter. */
  entityType: string;
  /** Entity primary key (UUID or composite). */
  entityId: string;
  /** Recent audit entries for this record. When undefined the bar renders
   *  the "coming soon" placeholder (back-compat). */
  entries?: AuditBarEntry[];
  /** Link to the full audit view filtered to this record. */
  viewAllHref?: string;
  isLoading?: boolean;
}

/**
 * Entity activity panel. With no `entries` it renders a placeholder (used
 * before a page wires real data). When `entries` is provided it lists the
 * most recent audit entries and links to the full audit view.
 */
export function AuditBar({
  entityType,
  entityId,
  entries,
  viewAllHref,
  isLoading,
}: AuditBarProps) {
  const showData = entries !== undefined;

  return (
    <section
      aria-label="Activity"
      data-entity-type={entityType}
      data-entity-id={entityId}
      className="rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-4"
    >
      <header className="mb-2 flex items-center gap-2 text-[var(--text-secondary)]">
        <History size={16} strokeWidth={1.75} aria-hidden />
        <h3 className="text-[13px] font-semibold uppercase tracking-wider">Activity</h3>
      </header>

      {!showData ? (
        <p className="text-[13px] text-[var(--text-tertiary)]">
          Audit history coming soon — the audit-log query endpoint is pending.
        </p>
      ) : isLoading ? (
        <p className="text-[13px] text-[var(--text-tertiary)]">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="text-[13px] text-[var(--text-tertiary)]">No recent activity.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {entries.map((e) => (
            <li
              key={e.id}
              className="flex items-center justify-between gap-3 text-[13px]"
            >
              <span className="text-[var(--text-primary)]">
                {e.operation}
                {e.actorLabel ? ` · ${e.actorLabel}` : ""}
              </span>
              <time className="text-[var(--text-tertiary)]" dateTime={e.occurredAt}>
                {e.occurredAt}
              </time>
            </li>
          ))}
        </ul>
      )}

      {viewAllHref ? (
        <a
          href={viewAllHref}
          className="mt-3 inline-block text-[13px] text-[var(--text-link)] underline-offset-2"
        >
          View Full History
        </a>
      ) : !showData ? (
        <button
          type="button"
          disabled
          className="mt-3 text-[13px] text-[var(--text-tertiary)] underline-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          View Full History
        </button>
      ) : null}
    </section>
  );
}
