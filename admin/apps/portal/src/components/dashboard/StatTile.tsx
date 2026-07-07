import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowUpRight, TrendingDown, TrendingUp } from "lucide-react";

interface StatTileProps {
  label: string;
  icon: ReactNode;
  hint?: ReactNode;
  /** When set, the tile links here and shows the hover affordance. */
  href?: string;
  /**
   * Period-over-period change, as a percent. A positive value reads as
   * success (green ↑), negative as danger (red ↓). null/undefined hides the
   * chip — use it when there's no comparable prior period.
   */
  delta?: number | null;
  /** Caption beside the delta chip, e.g. "vs last month". */
  deltaLabel?: string;
  /** The metric value (Money / Count / custom node). */
  children: ReactNode;
}

const CARD =
  "flex flex-col gap-3 rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-sm)] transition-shadow duration-150 hover:shadow-[var(--shadow-md)]";

function DeltaChip({ delta }: { delta: number }) {
  const up = delta >= 0;
  const text = `${up ? "+" : ""}${delta.toFixed(1)}%`;
  return (
    <span
      className={`inline-flex items-center gap-0.5 rounded-[var(--radius-full)] px-1.5 py-0.5 text-[12px] font-medium tabular-nums ${
        up
          ? "bg-[var(--status-success-bg)] text-[var(--text-success)]"
          : "bg-[var(--status-danger-bg)] text-[var(--text-danger)]"
      }`}
    >
      {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
      {text}
    </span>
  );
}

export function StatTile({
  label,
  icon,
  hint,
  href,
  delta,
  deltaLabel,
  children,
}: StatTileProps) {
  const body = (
    <>
      <div className="flex items-center justify-between">
        <span className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-md)] bg-[var(--surface-sunken)] text-[var(--icon-default)]">
          {icon}
        </span>
        {href ? (
          <ArrowUpRight
            size={18}
            className="text-[var(--icon-disabled)] transition-colors group-hover:text-[var(--text-primary)]"
          />
        ) : null}
      </div>
      <div>
        <p className="text-[13px] font-medium text-[var(--text-tertiary)]">
          {label}
        </p>
        <p className="mt-1 text-[24px] font-semibold leading-tight text-[var(--text-primary)]">
          {children}
        </p>
        {delta !== null && delta !== undefined ? (
          <p className="mt-1.5 flex items-center gap-1.5 text-[12px] text-[var(--text-tertiary)]">
            <DeltaChip delta={delta} />
            {deltaLabel}
          </p>
        ) : hint ? (
          <p className="mt-0.5 text-[12px] text-[var(--text-tertiary)]">{hint}</p>
        ) : null}
      </div>
    </>
  );

  return href ? (
    <Link href={href} className={`group ${CARD}`}>
      {body}
    </Link>
  ) : (
    <div className={CARD}>{body}</div>
  );
}

export function StatTileGrid({ children }: { children: ReactNode }) {
  return (
    <div
      className="grid gap-4"
      style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}
    >
      {children}
    </div>
  );
}
