import type { ReactNode } from "react";
import { ArrowUpRight } from "lucide-react";
import { cn } from "../../utils/cn";

export interface ChartCardProps {
  title: string;
  subtitle?: ReactNode;
  /** When set, a "See all" link renders in the header. */
  seeAllHref?: string;
  /** Optional node rendered at the top-right (e.g. a period toggle). */
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}

/**
 * Card chrome for a dashboard chart: a header (title, optional subtitle,
 * optional "See all" link or action) above the chart body. Framework-agnostic
 * — the "See all" link is a plain anchor so the component works in Storybook
 * and any app.
 */
export function ChartCard({
  title,
  subtitle,
  seeAllHref,
  action,
  className,
  children,
}: ChartCardProps) {
  return (
    <section
      className={cn(
        "flex flex-col gap-4 rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-sm)]",
        className,
      )}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-[14px] font-semibold text-[var(--text-primary)]">
            {title}
          </h2>
          {subtitle ? (
            <p className="text-[12px] text-[var(--text-tertiary)]">{subtitle}</p>
          ) : null}
        </div>
        {action ??
          (seeAllHref ? (
            <a
              href={seeAllHref}
              className="inline-flex shrink-0 items-center gap-0.5 text-[13px] font-medium text-[var(--text-link)] hover:text-[var(--text-link-hover)]"
            >
              See all
              <ArrowUpRight size={14} />
            </a>
          ) : null)}
      </header>
      {children}
    </section>
  );
}
