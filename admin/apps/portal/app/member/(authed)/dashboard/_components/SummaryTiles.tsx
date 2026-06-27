import Link from "next/link";
import { Money, Count } from "@sacco/ui";

interface Props {
  savingsTotal: string;
  sharesHeld: number;
  sharesValue: string;
  activeLoans: number;
  feesOutstanding: string;
}

export function SummaryTiles(props: Props) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <Link href="/member/savings" className="rounded-lg border p-4">
        <div className="text-sm text-[var(--text-secondary)]">Savings</div>
        <Money amount={props.savingsTotal} />
      </Link>
      <Link href="/member/shares" className="rounded-lg border p-4">
        <div className="text-sm text-[var(--text-secondary)]">Shares</div>
        <div>
          <Count value={props.sharesHeld} /> ·{" "}
          <Money amount={props.sharesValue} />
        </div>
      </Link>
      <Link href="/member/loans" className="rounded-lg border p-4">
        <div className="text-sm text-[var(--text-secondary)]">Active loans</div>
        <Count value={props.activeLoans} />
      </Link>
      <Link href="/member/fees" className="rounded-lg border p-4">
        <div className="text-sm text-[var(--text-secondary)]">
          Fees outstanding
        </div>
        <Money amount={props.feesOutstanding} />
      </Link>
    </div>
  );
}
