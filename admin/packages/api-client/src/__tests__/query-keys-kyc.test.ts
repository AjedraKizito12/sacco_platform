import { describe, expect, it } from "vitest";
import { queryKeys } from "../query-keys";

describe("KYC query keys", () => {
  it("organization keys nest under a common root for invalidation", () => {
    expect(queryKeys.organization.root()).toEqual(["organization"]);
    expect(queryKeys.organization.kyc()).toEqual(["organization", "kyc"]);
  });

  it("platform kyc keys nest under a common root", () => {
    expect(queryKeys.kyc.root()).toEqual(["kyc"]);
    expect(queryKeys.kyc.saccoRequirements()).toEqual(["kyc", "saccoRequirements"]);
  });

  it("tenant kyc key is scoped by tenant id", () => {
    expect(queryKeys.tenants.kyc("t1")).toEqual(["tenants", "kyc", "t1"]);
  });
});
