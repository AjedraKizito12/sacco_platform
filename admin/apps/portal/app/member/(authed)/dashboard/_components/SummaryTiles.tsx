import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowUpRight, Banknote, PiggyBank, Receipt } from "lucide-react";
import { Money, Count } from "@sacco/ui";

interface Props {
  savingsTotal: string;
  sharesHeld: number;
  sharesValue: string;
  activeLoans: number;
  feesOutstanding: string;
}

function StatTile({
  href,
  label,
  icon,
  children,
  hint,
}: {
  href: string;
  label: string;
  icon: ReactNode;
  children: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <Link
      href={href}
      className="group flex flex-col gap-3 rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-5 shadow-[var(--shadow-sm)] transition-shadow duration-150 hover:shadow-[var(--shadow-md)]"
    >
      <div className="flex items-center justify-between">
        <span className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-md)] bg-[var(--surface-sunken)] text-[var(--icon-default)]">
          {icon}
        </span>
        <ArrowUpRight
          size={18}
          className="text-[var(--icon-disabled)] transition-colors group-hover:text-[var(--text-primary)]"
        />
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
    </Link>
  );
}

export function SummaryTiles(props: Props) {
  return (
    <div className="flex flex-col gap-4">
      {/* Dark hero — total savings */}
      <Link
        href="/member/savings"
        className="group relative flex min-h-[168px] flex-col justify-between overflow-hidden rounded-[var(--radius-xl)] bg-[var(--status-dark-bg)] p-6 text-[color:var(--status-dark-text)] shadow-[var(--shadow-md)] transition-shadow duration-150 hover:shadow-[var(--shadow-lg)]"
      >
        <div className="flex items-center justify-between">
          <span className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-md)] bg-white/10 text-white/90">
            <PiggyBank size={18} />
          </span>
          <span className="text-[12px] font-medium text-white/55">
            Total savings
          </span>
        </div>
        <div>
          <p className="text-[36px] font-semibold leading-none tracking-[-0.01em]">
            <Money amount={props.savingsTotal} />
          </p>
          <span className="mt-3 inline-flex items-center gap-1 text-[13px] text-white/75 transition-colors group-hover:text-white">
            View savings
            <ArrowUpRight size={15} />
          </span>
        </div>
      </Link>

      <div
        className="grid gap-4"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}
      >
      <StatTile
        href="/member/shares"
        label="Shares"
        icon={<PiggyBank size={18} />}
        hint={
          <>
            <Count value={props.sharesHeld} /> shares held
          </>
        }
      >
        <Money amount={props.sharesValue} />
      </StatTile>

      <StatTile
        href="/member/loans"
        label="Active loans"
        icon={<Banknote size={18} />}
        hint={props.activeLoans === 0 ? "No active loans" : "In repayment"}
      >
        <Count value={props.activeLoans} />
      </StatTile>

      <StatTile
        href="/member/fees"
        label="Fees outstanding"
        icon={<Receipt size={18} />}
        hint={props.feesOutstanding === "0.00" ? "All settled" : "Due"}
      >
        <Money amount={props.feesOutstanding} />
      </StatTile>
      </div>
    </div>
  );
}
