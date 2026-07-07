import { resolveSegments, type ChartSegment } from "./chart-data";

export interface CompositionBarProps {
  data: ChartSegment[];
  /** Formats the legend value (e.g. count or money). Defaults to String. */
  valueFormatter?: (value: number) => string;
  /** Copy shown when every category is zero. */
  emptyLabel?: string;
}

/**
 * A single horizontal stacked bar showing the share of each category, with a
 * legend beneath. Pure DOM (no Recharts) — proportional widths come from the
 * resolved percentages — so it is fully testable and crisp at any size.
 */
export function CompositionBar({
  data,
  valueFormatter = (v) => String(v),
  emptyLabel = "No data yet",
}: CompositionBarProps) {
  const segments = resolveSegments(data);
  const total = segments.reduce((acc, s) => acc + s.value, 0);

  if (total === 0) {
    return (
      <p className="py-6 text-center text-[13px] text-[var(--text-tertiary)]">
        {emptyLabel}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex h-3 w-full overflow-hidden rounded-[var(--radius-full)] bg-[var(--surface-sunken)]">
        {segments
          .filter((s) => s.value > 0)
          .map((s) => (
            <span
              key={s.label}
              title={`${s.label}: ${Math.round(s.percentage)}%`}
              className="h-full"
              style={{ width: `${s.percentage}%`, backgroundColor: s.color }}
            />
          ))}
      </div>

      <ul className="flex flex-wrap gap-x-5 gap-y-2">
        {segments.map((s) => (
          <li
            key={s.label}
            className="flex items-center gap-2 text-[13px] text-[var(--text-secondary)]"
          >
            <span
              aria-hidden
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            <span className="text-[var(--text-primary)]">{s.label}</span>
            <span className="font-medium tabular-nums text-[var(--text-tertiary)]">
              {valueFormatter(s.value)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
