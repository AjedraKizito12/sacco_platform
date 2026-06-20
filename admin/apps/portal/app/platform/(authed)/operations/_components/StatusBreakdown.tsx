import { Card, Count, StatusBadge } from "@sacco/ui";

export interface StatusBreakdownProps {
  title: string;
  entity: "tenant" | "subscription";
  counts: Record<string, number>;
}

export function StatusBreakdown({ title, entity, counts }: StatusBreakdownProps) {
  const rows = Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));

  return (
    <Card className="flex flex-col gap-2 p-5">
      <h2 className="text-[var(--text-h5)] font-semibold">{title}</h2>
      {rows.length === 0 ? (
        <p className="text-[var(--text-tertiary)]">No data</p>
      ) : (
        <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
          {rows.map(([status, count]) => (
            <div key={status} className="flex items-center justify-between py-2">
              <StatusBadge entity={entity} status={status} />
              <Count value={count} data-testid="breakdown-count" />
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
