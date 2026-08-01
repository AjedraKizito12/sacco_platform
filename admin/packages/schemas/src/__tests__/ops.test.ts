import { describe, expect, it } from "vitest";
import { isStale, BACKUP_STALE_HOURS, VERIFY_STALE_DAYS } from "../ops";

describe("ops freshness", () => {
  it("thresholds match the roadmap", () => {
    expect(BACKUP_STALE_HOURS).toBe(24);
    expect(VERIFY_STALE_DAYS).toBe(7);
  });
  it("null is always stale", () => {
    expect(isStale(null, 1000)).toBe(true);
  });
  it("recent is fresh, old is stale", () => {
    const now = Date.parse("2026-07-12T12:00:00Z");
    expect(isStale("2026-07-12T11:00:00Z", 24 * 3600_000, now)).toBe(false);
    expect(isStale("2026-07-10T11:00:00Z", 24 * 3600_000, now)).toBe(true);
  });
});
