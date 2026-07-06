// Pure helpers shared by the composition charts. Kept free of React/Recharts
// so the colour-assignment and percentage maths are unit-tested directly.

/** Categorical series palette — references the --chart-* design tokens. */
export const CHART_SERIES = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
] as const;

export interface ChartSegment {
  label: string;
  value: number;
}

export interface ResolvedSegment extends ChartSegment {
  color: string;
  /** Share of the total, 0–100. Zero when the total is zero. */
  percentage: number;
}

export function resolveSegments(data: ChartSegment[]): ResolvedSegment[] {
  const total = data.reduce((acc, s) => acc + s.value, 0);
  return data.map((segment, i) => ({
    ...segment,
    color: CHART_SERIES[i % CHART_SERIES.length]!,
    percentage: total === 0 ? 0 : (segment.value / total) * 100,
  }));
}
