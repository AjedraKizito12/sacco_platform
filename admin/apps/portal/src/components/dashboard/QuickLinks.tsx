import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

export interface QuickLinkItem {
  icon: ReactNode;
  label: string;
  description: string;
  href: string;
}

interface QuickLinksProps {
  items: QuickLinkItem[];
}

/**
 * Audience quick-pick grid for the dashboards — the handful of destinations a
 * platform admin / operator / member reaches for most. Pure navigation; no
 * data fetching.
 */
export function QuickLinks({ items }: QuickLinksProps) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-[13px] font-semibold uppercase tracking-[0.04em] text-[var(--text-tertiary)]">
        Quick links
      </h2>
      <div
        className="grid gap-3"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}
      >
        {items.map((item) => (
          <Link
            key={item.label}
            href={item.href}
            className="group flex items-start gap-3 rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-sm)] transition-shadow duration-150 hover:shadow-[var(--shadow-md)]"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--surface-sunken)] text-[var(--icon-default)]">
              {item.icon}
            </span>
            <span className="flex flex-1 flex-col gap-0.5">
              <span className="flex items-center gap-1 text-[14px] font-medium text-[var(--text-primary)]">
                {item.label}
                <ArrowUpRight
                  size={14}
                  className="text-[var(--icon-disabled)] transition-colors group-hover:text-[var(--text-primary)]"
                />
              </span>
              <span className="text-[12px] text-[var(--text-tertiary)]">
                {item.description}
              </span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
