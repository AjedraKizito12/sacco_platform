import { SearchX } from "lucide-react";
import { Button } from "../../Button";

export interface FilterEmptyStateProps {
  onClearFilter(): void;
}

export function FilterEmptyState({ onClearFilter }: FilterEmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <SearchX
        size={48}
        strokeWidth={1.75}
        className="text-[var(--icon-default)]"
        aria-hidden
      />
      <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">
        No results match your filter
      </h3>
      <p className="max-w-md text-[var(--text-secondary)]">
        Try adjusting the filter to broaden the result set.
      </p>
      <Button variant="secondary" onClick={onClearFilter}>
        Clear filter
      </Button>
    </div>
  );
}
