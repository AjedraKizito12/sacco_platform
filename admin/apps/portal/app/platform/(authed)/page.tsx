import { Card } from "@sacco/ui";

export default function PlatformDashboard() {
  return (
    <Card className="p-6">
      <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
        Platform dashboard
      </h1>
      <p className="text-[var(--text-secondary)]">
        Sub-plan 34 ships the real platform dashboard with tenant counts, MRR,
        outstanding invoices, and pending approvals via
        <code className="mx-1">GET /platform/admin/dashboard-stats</code>.
      </p>
    </Card>
  );
}
