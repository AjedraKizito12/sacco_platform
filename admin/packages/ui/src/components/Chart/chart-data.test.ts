import { describe, expect, it } from "vitest";
import { CHART_SERIES, resolveSegments } from "./chart-data";

describe("resolveSegments", () => {
  it("assigns series colors in order and computes percentages", () => {
    const resolved = resolveSegments([
      { label: "Active", value: 75 },
      { label: "Pending", value: 25 },
    ]);
    expect(resolved[0]).toMatchObject({
      label: "Active",
      value: 75,
      percentage: 75,
      color: CHART_SERIES[0],
    });
    expect(resolved[1]).toMatchObject({
      label: "Pending",
      value: 25,
      percentage: 25,
      color: CHART_SERIES[1],
    });
  });

  it("cycles colors once the palette is exhausted", () => {
    const data = Array.from({ length: 7 }, (_, i) => ({
      label: `s${i}`,
      value: 1,
    }));
    const resolved = resolveSegments(data);
    // 7th segment wraps back to the first palette entry
    expect(resolved[6]!.color).toBe(CHART_SERIES[0]);
  });

  it("returns zero percentages when the total is zero (no divide-by-zero)", () => {
    const resolved = resolveSegments([
      { label: "A", value: 0 },
      { label: "B", value: 0 },
    ]);
    expect(resolved.every((s) => s.percentage === 0)).toBe(true);
  });
});
