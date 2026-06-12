import { Card } from "@sacco/ui";

export default function Loading() {
  return (
    <div className="flex flex-col gap-6">
      <div className="h-8 w-48 animate-pulse rounded-[var(--radius-sm)] bg-[var(--surface-sunken)]" />
      <Card className="p-4">
        <div className="flex flex-col gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="h-10 w-full animate-pulse rounded-[var(--radius-sm)] bg-[var(--surface-sunken)]"
            />
          ))}
        </div>
      </Card>
    </div>
  );
}
