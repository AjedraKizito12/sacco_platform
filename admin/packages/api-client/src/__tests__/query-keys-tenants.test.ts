import { describe, expect, it } from "vitest";
import { queryKeys } from "../query-keys";

describe("tenant query keys", () => {
  it("nest under a common root", () => {
    expect(queryKeys.tenants.root()).toEqual(["tenants"]);
    expect(queryKeys.tenants.detail("t1")).toEqual(["tenants", "detail", "t1"]);
  });

  it("expose Phase 7 offboarding keys", () => {
    expect(queryKeys.tenants.lifecycle("t1")).toEqual([
      "tenants",
      "lifecycle",
      "t1",
    ]);
    expect(queryKeys.tenants.archived()).toEqual(["tenants", "archived"]);
  });
});
