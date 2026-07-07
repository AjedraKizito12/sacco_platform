import { Card } from "@sacco/ui";

// Generic content skeleton shown as the Suspense fallback while a route's
// server component resolves. The app shell (sidebar + header) stays mounted in
// the layout, so only the content area swaps to this — navigation feels
// instant even when the data fetch behind the page is still in flight.
export function PageSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-6" aria-hidden="true">
      <div className="flex items-center justify-between gap-4">
        <div className="h-8 w-48 animate-pulse rounded-[var(--radius-sm)] bg-[var(--surface-sunken)]" />
        <div className="h-9 w-32 animate-pulse rounded-[var(--radius-md)] bg-[var(--surface-sunken)]" />
      </div>
      <Card className="p-4">
        <div className="flex flex-col gap-3">
          {Array.from({ length: rows }).map((_, i) => (
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
