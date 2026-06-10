import { describe, expect, it } from "vitest";
import { formatDateForInput, parseTypedDate } from "./parse-date";

describe("parseTypedDate", () => {
  it("accepts YYYY-MM-DD", () => {
    expect(parseTypedDate("2026-05-28")).toBe("2026-05-28");
  });
  it("accepts DD/MM/YYYY", () => {
    expect(parseTypedDate("28/05/2026")).toBe("2026-05-28");
  });
  it("returns null for nonsense", () => {
    expect(parseTypedDate("yesterday")).toBeNull();
    expect(parseTypedDate("32/13/2026")).toBeNull();
    expect(parseTypedDate("")).toBeNull();
  });
});

describe("formatDateForInput", () => {
  it("formats ISO as DD/MM/YYYY", () => {
    expect(formatDateForInput("2026-05-28")).toBe("28/05/2026");
  });
  it("returns empty for empty input", () => {
    expect(formatDateForInput("")).toBe("");
  });
});
