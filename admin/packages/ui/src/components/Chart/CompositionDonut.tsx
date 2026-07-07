"use client";

import { Cell, Pie, PieChart } from "recharts";
import { resolveSegments, type ChartSegment } from "./chart-data";

export interface CompositionDonutProps {
  data: ChartSegment[];
  /** Formats the legend value (e.g. money). Defaults to String(value). */
  valueFormatter?: (value: number) => string;
  /** Copy shown when every segment is zero. */
  emptyLabel?: string;
  /** Donut diameter in px. */
  size?: number;
}

/**
 * A donut chart (Recharts) paired with a real-DOM legend listing each
 * segment's label, value and percentage. The legend — not the SVG — is the
 * accessible, testable surface; the donut is the visual flourish.
 */
export function CompositionDonut({
  data,
  valueFormatter = (v) => String(v),
  emptyLabel = "No data yet",
  size = 140,
}: CompositionDonutProps) {
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
    <div className="flex flex-wrap items-center gap-5">
      <div className="shrink-0">
        <PieChart width={size} height={size}>
          <Pie
            data={segments}
            dataKey="value"
            nameKey="label"
            innerRadius="62%"
            outerRadius="100%"
            paddingAngle={2}
            stroke="none"
            isAnimationActive={false}
          >
            {segments.map((s) => (
              <Cell key={s.label} fill={s.color} />
            ))}
          </Pie>
        </PieChart>
      </div>

      <ul className="flex min-w-[160px] flex-1 flex-col gap-2">
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
            <span className="flex-1 text-[var(--text-primary)]">{s.label}</span>
            <span className="font-medium tabular-nums text-[var(--text-primary)]">
              {valueFormatter(s.value)}
            </span>
            <span className="w-10 text-right tabular-nums text-[var(--text-tertiary)]">
              {Math.round(s.percentage)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
