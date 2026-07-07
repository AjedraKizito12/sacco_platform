// Pure helpers turning the backend's MonthPoint[] trend series into the shape
// the @sacco/ui charts consume, plus the period-over-period delta for the
// metric-tile chips. Kept React-free for direct unit testing.
import type { MonthPoint } from "@sacco/schemas";
import type { TrendPoint } from "@sacco/ui";

const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/**
 * Percent change between the last two points of a series, or null when it
 * can't be computed (fewer than two points, or the prior value is zero).
 */
export function deltaPct(
  series: Pick<MonthPoint, "value">[] | null | undefined,
): number | null {
  if (!series || series.length < 2) return null;
  const prev = Number(series[series.length - 2]!.value);
  const last = Number(series[series.length - 1]!.value);
  if (prev === 0) return null;
  return ((last - prev) / prev) * 100;
}

/** Map MonthPoint[] (YYYY-MM + string value) to chart {label, value} points. */
export function toChartData(series: MonthPoint[] | null | undefined): TrendPoint[] {
  return (series ?? []).map((p) => {
    const monthIndex = Number(p.month.slice(5, 7)) - 1;
    return { label: MONTH_NAMES[monthIndex] ?? p.month, value: Number(p.value) };
  });
}
