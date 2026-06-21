// admin/apps/portal/app/(tenant-authed)/members/[id]/_components/MemberSharesSection.tsx
import Link from "next/link";
import { Button, Card, Count } from "@sacco/ui";
import type { ShareAccountListItemOut } from "@sacco/schemas";

export function MemberSharesSection({
  memberId,
  accounts,
}: {
  memberId: string;
  accounts: ShareAccountListItemOut[];
}) {
  return (
    <Card className="flex flex-col gap-3 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-[var(--text-h5)] font-semibold">Share accounts</h2>
        <Button asChild variant="secondary">
          <Link href={`/shares/accounts/new?member_id=${memberId}`}>Open account</Link>
        </Button>
      </div>
      {accounts.length === 0 ? (
        <p className="text-[var(--text-secondary)]">No share accounts.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-[var(--border-subtle)]">
          {accounts.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-4 py-3">
              <div className="flex flex-col">
                <span className="font-medium">{a.product_name}</span>
                <span className="text-[var(--text-secondary)]">
                  <Count value={a.shares_held} /> shares
                </span>
              </div>
              <Link
                href={`/shares/accounts/${a.id}`}
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
