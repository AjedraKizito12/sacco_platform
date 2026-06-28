import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

interface DashboardHeroProps {
  /** Muted label in the top-right corner. */
  label: string;
  /** Small icon chip, top-left. */
  icon?: ReactNode;
  /** When set, the whole card links here and shows the action affordance. */
  href?: string;
  /** Link affordance copy, e.g. "View savings". Only shown with href. */
  action?: string;
  /** The headline value (Money / Count / custom node). Rendered large. */
  children: ReactNode;
}

const CARD =
  "relative flex min-h-[168px] flex-col justify-between overflow-hidden rounded-[var(--radius-xl)] bg-[var(--status-dark-bg)] p-6 text-[color:var(--status-dark-text)] shadow-[var(--shadow-md)] transition-shadow duration-150 hover:shadow-[var(--shadow-lg)]";

export function DashboardHero({
  label,
  icon,
  href,
  action,
  children,
}: DashboardHeroProps) {
  const body = (
    <>
      <div className="flex items-center justify-between">
        {icon ? (
          <span className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-md)] bg-white/10 text-white/90">
            {icon}
          </span>
        ) : (
          <span />
        )}
        <span className="text-[12px] font-medium text-white/55">{label}</span>
      </div>
      <div>
        <div className="text-[34px] font-semibold leading-none tracking-[-0.01em]">
          {children}
        </div>
        {href && action ? (
          <span className="mt-3 inline-flex items-center gap-1 text-[13px] text-white/75 transition-colors group-hover:text-white">
            {action}
            <ArrowUpRight size={15} />
          </span>
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
