"use client";

import {
  Card,
  FormattedDateTime,
  KpiCard,
  Money,
  StatusBadge,
} from "@sacco/ui";

export default function PlatformDashboard() {
  return (
    <div className="flex flex-col gap-6">
      <Card className="p-6">
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
          Platform dashboard
        </h1>
        <p className="text-[var(--text-secondary)]">
          Sub-plan 34 wires the real
          <code className="mx-1">GET /platform/admin/dashboard-stats</code>
          data.
        </p>
      </Card>

      <div className="grid grid-cols-3 gap-4">
        <KpiCard label="Total tenants" value="—" />
        <KpiCard
          label="Monthly recurring revenue"
          value={<Money amount="0" currency="UGX" size="large" />}
        />
        <KpiCard label="Outstanding invoices" value="—" />
      </div>

      <Card className="p-6">
        <h2 className="mb-3 text-[18px] font-semibold">Sample status row</h2>
        <div className="flex flex-wrap gap-2">
          <StatusBadge entity="tenant" status="active" />
          <StatusBadge entity="tenant" status="provisioning" />
          <StatusBadge entity="invoice" status="overdue" />
          <StatusBadge entity="approval_request" status="pending" />
        </div>
        <p className="mt-3 text-[12px] text-[var(--text-tertiary)]">
          Last refreshed <FormattedDateTime value={new Date().toISOString()} />
        </p>
      </Card>
    </div>
  );
}
