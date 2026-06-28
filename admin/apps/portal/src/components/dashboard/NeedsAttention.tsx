import type { ReactNode } from "react";
import Link from "next/link";
import { CheckCircle2, ChevronRight } from "lucide-react";
import { Badge } from "@sacco/ui";

type AttentionTone = "danger" | "warning" | "info" | "neutral";

export interface AttentionItem {
  icon: ReactNode;
  label: string;
  href: string;
  /** Magnitude that drives visibility — rows with count 0 are omitted. */
  count: number;
  /** The rendered value chip (a <Count>, <Money>, or plain string). */
  value: ReactNode;
  tone?: AttentionTone;
}

interface NeedsAttentionProps {
  items: AttentionItem[];
  /** Copy for the empty state when nothing needs attention. */
  allClearLabel?: string;
}

const TONE_TO_VARIANT: Record<AttentionTone, "danger" | "warning" | "info" | "neutral"> =
  {
    danger: "danger",
    warning: "warning",
    info: "info",
    neutral: "neutral",
  };

/**
 * Audience "needs attention" panel for the dashboards. Surfaces the open
 * action queues (pending approvals, arrears, overdue invoices…) as linked
 * rows. Rows with a zero count are hidden; when every item is zero the
 * panel collapses to a positive empty state.
 */
export function NeedsAttention({
  items,
  allClearLabel = "All clear — nothing needs your attention.",
}: NeedsAttentionProps) {
  const active = items.filter((item) => item.count > 0);

  return (
    <section className="flex flex-col gap-3 rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-sm)]">
      <h2 className="text-[13px] font-semibold uppercase tracking-[0.04em] text-[var(--text-tertiary)]">
        Needs attention
      </h2>

      {active.length === 0 ? (
        <div className="flex items-center gap-2 py-2 text-[14px] text-[var(--text-secondary)]">
          <CheckCircle2 size={18} className="text-[var(--text-success)]" />
          {allClearLabel}
        </div>
      ) : (
        <ul className="flex flex-col divide-y divide-[var(--border-subtle)]">
          {active.map((item) => (
            <li key={item.label}>
              <Link
                href={item.href}
                className="group flex items-center gap-3 py-3 transition-colors first:pt-1 last:pb-1 hover:text-[var(--text-link)]"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--surface-sunken)] text-[var(--icon-default)]">
                  {item.icon}
                </span>
                <span className="flex-1 text-[14px] font-medium text-[var(--text-primary)]">
                  {item.label}
                </span>
                <Badge variant={TONE_TO_VARIANT[item.tone ?? "neutral"]}>
                  {item.value}
                </Badge>
                <ChevronRight
                  size={16}
                  className="text-[var(--icon-disabled)] transition-colors group-hover:text-[var(--text-primary)]"
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
