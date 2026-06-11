import { Card } from "@sacco/ui";

export default function Loading() {
  return (
    <div className="flex flex-col gap-6">
      <div className="h-8 w-64 animate-pulse rounded-[var(--radius-sm)] bg-[var(--surface-sunken)]" />
      <Card className="grid grid-cols-2 gap-5 p-6">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-12 w-full animate-pulse rounded-[var(--radius-sm)] bg-[var(--surface-sunken)]" />
        ))}
      </Card>
    </div>
  );
}
