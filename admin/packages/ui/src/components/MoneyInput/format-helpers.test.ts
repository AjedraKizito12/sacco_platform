import { describe, expect, it } from "vitest";
import { canonicalise, formatTyping, stripFormatting } from "./format-helpers";

describe("stripFormatting", () => {
  it("strips commas and spaces", () => {
    expect(stripFormatting("1,234,567")).toBe("1234567");
    expect(stripFormatting("UGX 1 234")).toBe("1234");
  });
  it("preserves a leading minus", () => {
    expect(stripFormatting("-1,234")).toBe("-1234");
  });
  it("collapses multiple decimal points to the first", () => {
    expect(stripFormatting("1.2.3")).toBe("1.23");
  });
  it("returns empty for empty input", () => {
    expect(stripFormatting("")).toBe("");
  });
});

describe("formatTyping", () => {
  it("inserts thousands separators", () => {
    expect(formatTyping("1234567")).toBe("1,234,567");
  });
  it("preserves a trailing decimal point", () => {
    expect(formatTyping("12.")).toBe("12.");
  });
  it("preserves trailing zeros in the fractional part", () => {
    expect(formatTyping("12.50")).toBe("12.50");
  });
  it("handles negative", () => {
    expect(formatTyping("-1234")).toBe("-1,234");
  });
  it("returns empty for empty input", () => {
    expect(formatTyping("")).toBe("");
  });
});

describe("canonicalise", () => {
  it("UGX → 0 decimals", () => {
    expect(canonicalise("12", "UGX")).toBe("12");
    expect(canonicalise("12.7", "UGX")).toBe("13");
  });
  it("USD → 2 decimals", () => {
    expect(canonicalise("12", "USD")).toBe("12.00");
    expect(canonicalise("12.5", "USD")).toBe("12.50");
    expect(canonicalise("12.567", "USD")).toBe("12.57");
  });
  it("empty string stays empty (so 'required' can fire)", () => {
    expect(canonicalise("", "UGX")).toBe("");
    expect(canonicalise("-", "UGX")).toBe("");
  });
});
