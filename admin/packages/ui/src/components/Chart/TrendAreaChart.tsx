"use client";

import { useId } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatCount, formatMoney } from "../../utils/format";

export interface TrendPoint {
  label: string;
  value: number;
}

/**
 * Serializable description of how to format the chart's values. A plain
 * descriptor (not a function) so a Server Component can pass it across the
 * RSC boundary into this Client Component.
 */
export type TrendValueFormat =
  | { kind: "number" }
  | { kind: "money"; currency: string };

export interface TrendAreaChartProps {
  data: TrendPoint[];
  /** Accessible name for the chart figure. */
  ariaLabel: string;
  /** How to format values in the tooltip and the accessible summary. */
  valueFormat?: TrendValueFormat;
  /** Copy shown when there is no series data. */
  emptyLabel?: string;
  height?: number;
}

function buildFormatter(
  fmt: TrendValueFormat,
): (value: number) => string {
  if (fmt.kind === "money") {
    return (value) => formatMoney(String(value), fmt.currency);
  }
  return (value) => formatCount(value);
}

/**
 * A responsive area/line trend chart (Recharts) for a monthly series. The
 * visible SVG is the flourish; an accessible summary of the latest value is
 * rendered for screen readers (and is the testable surface, since jsdom has no
 * SVG layout). Colours come from the --chart-* tokens.
 */
export function TrendAreaChart({
  data,
  ariaLabel,
  valueFormat = { kind: "number" },
  emptyLabel = "No history yet",
  height = 200,
}: TrendAreaChartProps) {
  const gradientId = useId();
  const valueFormatter = buildFormatter(valueFormat);
  const latest = data.at(-1);

  if (data.length === 0 || !latest) {
    return (
      <p className="py-6 text-center text-[13px] text-[var(--text-tertiary)]">
        {emptyLabel}
      </p>
    );
  }

  return (
    <figure role="img" aria-label={ariaLabel} className="m-0">
      <span className="sr-only">
        {ariaLabel}. Latest: <span>{valueFormatter(latest.value)}</span>.
      </span>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.28} />
                <stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid
              vertical={false}
              stroke="var(--chart-grid)"
              strokeDasharray="3 3"
            />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11, fill: "var(--chart-axis)" }}
              dy={6}
            />
            <YAxis hide />
            <Tooltip
              cursor={{ stroke: "var(--chart-grid)" }}
              contentStyle={{
                borderRadius: "var(--radius-md)",
                border: "none",
                backgroundColor: "var(--chart-tooltip-bg)",
                color: "var(--chart-tooltip-text)",
                fontSize: 12,
              }}
              labelStyle={{ color: "var(--chart-tooltip-text)", opacity: 0.7 }}
              formatter={(value: unknown) => [valueFormatter(Number(value)), ""]}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="var(--chart-1)"
              strokeWidth={2}
              fill={`url(#${gradientId})`}
              isAnimationActive={false}
              activeDot={{ r: 4 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
