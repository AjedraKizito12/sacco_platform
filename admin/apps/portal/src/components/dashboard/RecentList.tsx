import type { ReactNode } from "react";
import Link from "next/link";

export interface RecentItem {
  id: string;
  primary: ReactNode;
  secondary?: ReactNode;
  /** Trailing content — a value, badge, or timestamp. */
  trailing?: ReactNode;
  href?: string;
}

interface RecentListProps {
  items: RecentItem[];
  emptyLabel?: string;
}

/**
 * A compact "quick-peek" list of recent records for the dashboards (recent
 * applications, members, tenants, payments…). Rendered as styled rows — not a
 * `<table>` — so it stays distinct from the full DataTable list screens
 * (contract T). Each row optionally links to the record.
 */
export function RecentList({ items, emptyLabel = "Nothing yet" }: RecentListProps) {
  if (items.length === 0) {
    return (
      <p className="py-6 text-center text-[13px] text-[var(--text-tertiary)]">
        {emptyLabel}
      </p>
    );
  }

  return (
    <ul className="flex flex-col divide-y divide-[var(--border-subtle)]">
      {items.map((item) => {
        const inner = (
          <>
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-[14px] font-medium text-[var(--text-primary)]">
                {item.primary}
              </span>
              {item.secondary ? (
                <span className="truncate text-[12px] text-[var(--text-tertiary)]">
                  {item.secondary}
                </span>
              ) : null}
            </span>
            {item.trailing ? (
              <span className="shrink-0 text-[13px] tabular-nums text-[var(--text-secondary)]">
                {item.trailing}
              </span>
            ) : null}
          </>
        );
        return (
          <li key={item.id}>
            {item.href ? (
              <Link
                href={item.href}
                className="flex items-center gap-3 py-3 transition-colors first:pt-1 last:pb-1 hover:text-[var(--text-link)]"
              >
                {inner}
              </Link>
            ) : (
              <div className="flex items-center gap-3 py-3 first:pt-1 last:pb-1">
                {inner}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
