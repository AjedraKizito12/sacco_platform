// admin/apps/portal/app/(tenant-authed)/reports/page.tsx
import Link from "next/link";
import { Card } from "@sacco/ui";

export const metadata = { title: "Reports" };

const REPORTS = [
  { href: "/reports/trial-balance", label: "Trial balance" },
  { href: "/reports/loan-portfolio", label: "Loan portfolio" },
  { href: "/reports/income-statement", label: "Income statement" },
  { href: "/reports/savings-statement", label: "Savings statement" },
  { href: "/reports/fee-collection", label: "Fee collection" },
  { href: "/reports/runs", label: "Report runs" },
];

export default function ReportsIndexPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Reports</h1>
      <Card className="flex flex-col divide-y divide-[var(--border-subtle)] p-2">
        {REPORTS.map((r) => (
          <Link
            key={r.href}
            href={r.href}
            className="px-4 py-3 text-[var(--text-link)]"
          >
            {r.label}
          </Link>
        ))}
      </Card>
    </div>
  );
}
