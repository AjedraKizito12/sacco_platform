import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

interface StatTileProps {
  label: string;
  icon: ReactNode;
  hint?: ReactNode;
  /** When set, the tile links here and shows the hover affordance. */
  href?: string;
  /** The metric value (Money / Count / custom node). */
  children: ReactNode;
}

const CARD =
  "flex flex-col gap-3 rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-sm)] transition-shadow duration-150 hover:shadow-[var(--shadow-md)]";

export function StatTile({ label, icon, hint, href, children }: StatTileProps) {
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
        {hint ? (
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
