import { Card } from "@sacco/ui";

export default function TenantDashboard() {
  return (
    <Card className="p-6">
      <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
        Tenant dashboard
      </h1>
      <p className="text-[var(--text-secondary)]">
        Sub-plan 35 ships the real tenant dashboard (KPIs, charts, recent
        activity).
      </p>
    </Card>
  );
}
