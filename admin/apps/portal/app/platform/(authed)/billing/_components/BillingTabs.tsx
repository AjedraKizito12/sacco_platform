// admin/apps/portal/app/platform/(authed)/billing/_components/BillingTabs.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/platform/billing/plans", label: "Plans" },
  { href: "/platform/billing/subscriptions", label: "Subscriptions" },
  { href: "/platform/billing/invoices", label: "Invoices" },
  { href: "/platform/billing/payments", label: "Payments" },
] as const;

export function BillingTabs() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1 border-b border-[var(--border-subtle)]" aria-label="Billing sections">
      {TABS.map((tab) => {
        const active = pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? "page" : undefined}
            className={
              active
                ? "border-b-2 border-[var(--interactive-primary-bg)] px-4 py-2 text-[var(--text-primary)] font-medium"
                : "border-b-2 border-transparent px-4 py-2 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
