import type { ReactNode } from "react";
import Link from "next/link";
import { Card } from "@sacco/ui";

export interface StatCardProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  href?: string;
}

export function StatCard({ label, value, sub, href }: StatCardProps) {
  const body = (
    <Card className="flex flex-col gap-1 p-5">
      <span className="text-[13px] text-[var(--text-tertiary)]">{label}</span>
      <span className="text-[var(--text-h3)] font-semibold text-[var(--text-primary)]">
        {value}
      </span>
      {sub ? <span className="text-[13px] text-[var(--text-secondary)]">{sub}</span> : null}
    </Card>
  );
  if (href) {
    return (
      <Link
        href={href}
        aria-label={label}
        className="block rounded-[var(--radius-md)] transition-colors hover:bg-[var(--surface-hover)]"
      >
        {body}
      </Link>
    );
  }
  return body;
}
