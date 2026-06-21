// admin/apps/portal/app/(tenant-authed)/members/[id]/_components/MemberSavingsSection.tsx
import Link from "next/link";
import { Button, Card, Percentage } from "@sacco/ui";
import type { SavingsAccountOut } from "@sacco/schemas";

export function MemberSavingsSection({
  memberId,
  accounts,
}: {
  memberId: string;
  accounts: SavingsAccountOut[];
}) {
  return (
    <Card className="flex flex-col gap-3 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-[var(--text-h5)] font-semibold">Savings accounts</h2>
        <Button asChild variant="secondary">
          <Link href={`/savings/accounts/new?member_id=${memberId}`}>Open account</Link>
        </Button>
      </div>
      {accounts.length === 0 ? (
        <p className="text-[var(--text-secondary)]">No savings accounts.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-[var(--border-subtle)]">
          {accounts.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-4 py-3">
              <div className="flex flex-col">
                <span className="font-medium">{a.product_name}</span>
                <span className="text-[var(--text-secondary)]">
                  <Percentage value={a.interest_rate} /> interest
                </span>
              </div>
              <Link
                href={`/savings/accounts/${a.id}`}
                className="text-[var(--text-link)] hover:underline"
              >
                View
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
