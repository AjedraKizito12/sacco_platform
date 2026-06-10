import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "../Button";

export interface PaginationProps {
  page: number; // 1-indexed
  pageSize: number;
  totalRows: number;
  onPageChange(p: number): void;
  onPageSizeChange(size: number): void;
}

export function Pagination({
  page,
  pageSize,
  totalRows,
  onPageChange,
  onPageSizeChange,
}: PaginationProps) {
  const lastPage = Math.max(1, Math.ceil(totalRows / pageSize));
  const firstRow = totalRows === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastRow = Math.min(totalRows, page * pageSize);
  return (
    <div
      className="flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] px-4 py-3 text-[var(--text-secondary)]"
      data-density-target="pagination"
    >
      <div className="text-[13px]">
        Showing{" "}
        <span className="font-medium text-[var(--text-primary)]">
          {firstRow}
        </span>
        –
        <span className="font-medium text-[var(--text-primary)]">{lastRow}</span>{" "}
        of{" "}
        <span className="font-medium text-[var(--text-primary)]">
          {totalRows}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <label className="text-[13px]">
          Rows
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="ml-2 h-[var(--height-control-sm)] rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--surface-elevated)] px-2 text-[13px]"
          >
            {[10, 25, 50, 100].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
        >
          <ChevronLeft size={16} />
        </Button>
        <span className="text-[13px]">
          Page{" "}
          <span className="font-medium text-[var(--text-primary)]">{page}</span>{" "}
          / {lastPage}
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= lastPage}
          aria-label="Next page"
        >
          <ChevronRight size={16} />
        </Button>
      </div>
    </div>
  );
}
