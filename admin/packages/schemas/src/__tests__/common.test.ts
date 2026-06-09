import { describe, expect, it } from "vitest";
import {
  cursorPagination,
  currencyCode,
  idempotencyKey,
  isoDate,
  isoDateTime,
  moneyString,
  percentageString,
  uuid,
} from "../common";

describe("moneyString", () => {
  it("accepts integer and decimal strings", () => {
    const m = moneyString();
    expect(m.parse("50000")).toBe("50000");
    expect(m.parse("50000.5")).toBe("50000.5");
    expect(m.parse("50000.1234")).toBe("50000.1234");
  });

  it("rejects more than 4 decimal places", () => {
    expect(() => moneyString().parse("50000.12345")).toThrow();
  });

  it("rejects negative when allowNegative is not set", () => {
    expect(() => moneyString().parse("-50000")).toThrow();
  });

  it("accepts negative when allowNegative=true", () => {
    expect(moneyString({ allowNegative: true }).parse("-50000")).toBe("-50000");
  });

  it("enforces min and max bounds", () => {
    const m = moneyString({ min: "100", max: "1000" });
    expect(m.parse("500")).toBe("500");
    expect(() => m.parse("50")).toThrow(/≥ 100/);
    expect(() => m.parse("5000")).toThrow(/≤ 1000/);
  });

  it("rejects non-numeric strings", () => {
    expect(() => moneyString().parse("fifty-thousand")).toThrow();
    expect(() => moneyString().parse("")).toThrow();
  });
});

describe("percentageString", () => {
  it("accepts 0..100 range by default", () => {
    expect(percentageString().parse("12.50")).toBe("12.50");
    expect(() => percentageString().parse("150")).toThrow();
  });
  it("honours custom range", () => {
    const annualRate = percentageString({ max: 50 });
    expect(annualRate.parse("12.5")).toBe("12.5");
    expect(() => annualRate.parse("60")).toThrow();
  });
});

describe("currencyCode", () => {
  it("requires three uppercase letters", () => {
    expect(currencyCode.parse("UGX")).toBe("UGX");
    expect(() => currencyCode.parse("ugx")).toThrow();
    expect(() => currencyCode.parse("UG")).toThrow();
  });
});

describe("uuid", () => {
  it("accepts a UUID v4 string", () => {
    expect(() =>
      uuid.parse("550e8400-e29b-41d4-a716-446655440000"),
    ).not.toThrow();
  });
  it("rejects garbage", () => {
    expect(() => uuid.parse("not-a-uuid")).toThrow();
  });
});

describe("isoDate / isoDateTime", () => {
  it("isoDate accepts YYYY-MM-DD", () => {
    expect(isoDate.parse("2026-06-04")).toBe("2026-06-04");
    expect(() => isoDate.parse("2026/06/04")).toThrow();
  });
  it("isoDateTime accepts ISO-8601", () => {
    expect(() =>
      isoDateTime.parse("2026-06-04T14:32:07Z"),
    ).not.toThrow();
  });
});

describe("cursorPagination", () => {
  it("accepts empty object", () => {
    expect(cursorPagination().parse({})).toEqual({});
  });
  it("coerces limit from string (URL params)", () => {
    expect(cursorPagination().parse({ limit: "50" })).toEqual({ limit: 50 });
  });
  it("caps limit at 100", () => {
    expect(() => cursorPagination().parse({ limit: 200 })).toThrow();
  });
});

describe("idempotencyKey", () => {
  it("requires at least 8 chars", () => {
    expect(idempotencyKey.parse("12345678")).toBe("12345678");
    expect(() => idempotencyKey.parse("short")).toThrow();
  });
});
