import type { ReactNode } from "react";
import { cn } from "../../utils/cn";

export interface FormSectionProps {
  /** Optional group label, e.g. "Personal details". */
  title?: string;
  /** Optional one-line helper under the title. */
  description?: string;
  /** Lay fields out in one or two columns (collapses to one on narrow viewports). */
  columns?: 1 | 2;
  children: ReactNode;
  className?: string;
}

/**
 * Groups related fields inside a FormDialog. Gives each group a quiet heading
 * and a responsive grid so a long form reads as a few short sections rather
 * than one tall column. A field that should span the full width of a 2-column
 * section can set `className="sm:col-span-2"` on its <FormField>.
 */
export function FormSection({
  title,
  description,
  columns = 1,
  children,
  className,
}: FormSectionProps) {
  return (
    <section className={cn("flex flex-col gap-3", className)}>
      {title || description ? (
        <div className="flex flex-col gap-0.5">
          {title ? (
            <h3 className="text-[13px] font-semibold text-[var(--text-secondary)]">{title}</h3>
          ) : null}
          {description ? (
            <p className="text-[12px] text-[var(--text-tertiary)]">{description}</p>
          ) : null}
        </div>
      ) : null}
      <div
        className={cn(
          "grid gap-x-4 gap-y-4",
          columns === 2 ? "sm:grid-cols-2" : "grid-cols-1",
        )}
      >
        {children}
      </div>
    </section>
  );
}
