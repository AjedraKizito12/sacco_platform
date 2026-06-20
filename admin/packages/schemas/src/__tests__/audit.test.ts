import { describe, expect, it } from "vitest";
import { AUDIT_OPERATION_OPTIONS } from "../audit";

describe("AUDIT_OPERATION_OPTIONS", () => {
  it("lists insert/update/delete with labels", () => {
    expect(AUDIT_OPERATION_OPTIONS.map((o) => o.value)).toEqual([
      "insert",
      "update",
      "delete",
    ]);
    expect(AUDIT_OPERATION_OPTIONS.every((o) => o.label.length > 0)).toBe(true);
  });
});
