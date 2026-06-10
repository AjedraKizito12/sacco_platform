import { Button } from "../Button";

export interface BulkBannerProps {
  selectedOnPage: number;
  totalMatching: number;
  pageSize: number;
  allMatchingSelected: boolean;
  onSelectAllMatching(): void;
  onClearSelection(): void;
  actions: Array<{ id: string; label: string; destructive?: boolean }>;
  onActionClick(actionId: string): void;
}

export function BulkBanner(props: BulkBannerProps) {
  const {
    selectedOnPage,
    totalMatching,
    pageSize,
    allMatchingSelected,
    onSelectAllMatching,
    onClearSelection,
    actions,
    onActionClick,
  } = props;
  const fullPageSelected =
    selectedOnPage >= pageSize && totalMatching > pageSize;
  return (
    <div
      className="flex items-center gap-3 border-b border-[var(--border-subtle)] bg-[var(--surface-selected)] px-4 py-2 text-[13px]"
      role="region"
      aria-label="Bulk selection"
    >
      <span className="font-medium text-[var(--text-primary)]">
        {allMatchingSelected
          ? `${totalMatching} matching rows selected`
          : `${selectedOnPage} on this page selected`}
      </span>
      {fullPageSelected && !allMatchingSelected ? (
        <Button size="sm" variant="ghost" onClick={onSelectAllMatching}>
          Select all {totalMatching} matching
        </Button>
      ) : null}
      <Button size="sm" variant="ghost" onClick={onClearSelection}>
        Clear selection
      </Button>
      <div className="ml-auto flex items-center gap-1">
        {actions.map((a) => (
          <Button
            key={a.id}
            size="sm"
            variant={a.destructive ? "destructive" : "secondary"}
            onClick={() => onActionClick(a.id)}
          >
            {a.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
