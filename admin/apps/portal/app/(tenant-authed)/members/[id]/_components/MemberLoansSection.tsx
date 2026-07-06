// admin/apps/portal/app/(tenant-authed)/members/[id]/_components/MemberLoansSection.tsx
import Link from "next/link";
import { Card, Money, StatusBadge } from "@sacco/ui";
import type { LoanOut } from "@sacco/schemas";

export function MemberLoansSection({ loans }: { loans: LoanOut[] }) {
  return (
    <Card className="flex flex-col gap-3 p-6">
      <h2 className="text-[var(--text-h5)] font-semibold">Loans</h2>
      {loans.length === 0 ? (
        <p className="text-[var(--text-secondary)]">No loans.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-[var(--border-subtle)]">
          {loans.map((l) => (
            <li key={l.id} className="flex items-center justify-between gap-4 py-3">
              <div className="flex flex-col">
                <span className="font-medium">{l.loan_reference}</span>
                <span className="text-[var(--text-secondary)]">
                  <Money amount={l.outstanding_principal} /> outstanding
                </span>
              </div>
              <div className="flex items-center gap-3">
                <StatusBadge entity="loan" status={l.status} />
                <Link
                  href={`/credit/loans/${l.id}`}
                  className="text-[var(--text-link)]"
                >
                  View
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
