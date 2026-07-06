import { describe, it, expect } from "vitest";
import { deltaPct, toChartData } from "../trend";

describe("deltaPct", () => {
  it("computes the percent change between the last two points", () => {
    expect(deltaPct([{ value: "100" }, { value: "150" }])).toBe(50);
    expect(deltaPct([{ value: "200" }, { value: "150" }])).toBe(-25);
  });

  it("returns null when the prior point is zero (no divide-by-zero)", () => {
    expect(deltaPct([{ value: "0" }, { value: "50" }])).toBeNull();
  });

  it("returns null with fewer than two points", () => {
    expect(deltaPct([{ value: "100" }])).toBeNull();
    expect(deltaPct([])).toBeNull();
  });

  it("returns null for nullish input (resilient to API shape skew)", () => {
    expect(deltaPct(undefined)).toBeNull();
    expect(deltaPct(null)).toBeNull();
  });
});

describe("toChartData", () => {
  it("maps month-points to {label, value} with the month's short name", () => {
    const out = toChartData([
      { month: "2026-05", value: "1000.00" },
      { month: "2026-06", value: "1500.50" },
    ]);
    expect(out).toEqual([
      { label: "May", value: 1000 },
      { label: "Jun", value: 1500.5 },
    ]);
  });
});
