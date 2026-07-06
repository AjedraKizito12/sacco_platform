import type { ReactNode } from "react";
import { cn } from "../../utils/cn";

export interface ReadOnlyFieldProps {
  label: string;
  /** Either a primitive value or a fully-rendered display primitive
   *  (e.g., `<Money>`, `<FormattedDate>`). */
  value: ReactNode;
  className?: string;
}

export function ReadOnlyField({ label, value, className }: ReadOnlyFieldProps) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <span className="text-[13px] font-medium text-[var(--text-secondary)]">
        {label}
      </span>
      <div
        className={cn(
          "flex min-h-[var(--height-control)] items-center rounded-[var(--radius-md)] px-3 text-[var(--text-body)]",
          "bg-[var(--surface-sunken)] text-[var(--text-primary)]",
          "border border-[var(--border-subtle)]",
        )}
      >
        {value}
      </div>
    </div>
  );
}
