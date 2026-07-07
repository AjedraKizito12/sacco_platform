import { Check, Minus } from "lucide-react";
import { Card, Percentage } from "@sacco/ui";
import type { KycCompletionOut } from "@sacco/schemas";

/**
 * Shared completion tracker card: percent + progress bar + full-catalog
 * checklist. Server-computed (app/core/kyc); this component only renders —
 * it never re-derives completeness (CLAUDE.md core-tracker contract).
 */
export function KycCompletionCard({
  completion,
  title = "KYC completion",
}: {
  completion: KycCompletionOut;
  title?: string;
}) {
  return (
    <Card className="flex flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-[var(--text-h5)] font-semibold">{title}</h2>
        <Percentage
          value={String(completion.percent)}
          className="text-[var(--text-h5)] font-semibold"
        />
      </div>
      <div
        role="progressbar"
        aria-label={title}
        aria-valuenow={completion.percent}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-2 overflow-hidden rounded-full bg-[var(--status-neutral-bg)]"
      >
        <div
          className="h-full rounded-full bg-[var(--interactive-primary-bg)]"
          style={{ width: `${completion.percent}%` }}
        />
      </div>
      <p className="text-[13px] text-[var(--text-secondary)]">
        {completion.is_complete
          ? "All required items are complete."
          : `${completion.required_present} of ${completion.required_total} required items complete.`}
      </p>
      <ul className="flex flex-col gap-1.5">
        {completion.items.map((item) => (
          <li key={item.key} className="flex items-center gap-2 text-[13px]">
            {item.present ? (
              <Check size={14} className="shrink-0 text-[var(--text-success)]" aria-hidden />
            ) : (
              <Minus
                size={14}
                className={
                  item.required
                    ? "shrink-0 text-[var(--text-danger)]"
                    : "shrink-0 text-[var(--text-tertiary)]"
                }
                aria-hidden
              />
            )}
            <span
              className={
                item.present
                  ? "text-[var(--text-primary)]"
                  : item.required
                    ? "text-[var(--text-danger)]"
                    : "text-[var(--text-secondary)]"
              }
            >
              {item.label}
            </span>
            {item.required ? null : (
              <span className="text-[11px] text-[var(--text-tertiary)]">(optional)</span>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
