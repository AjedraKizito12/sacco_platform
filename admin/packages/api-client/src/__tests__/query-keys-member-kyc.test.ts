import { describe, expect, it } from "vitest";
import { queryKeys } from "../query-keys";

describe("member KYC query keys", () => {
  it("members config + per-member completion keys", () => {
    expect(queryKeys.members.kycRequirements()).toEqual(["members", "kycRequirements"]);
    expect(queryKeys.members.kyc("m1")).toEqual(["members", "kyc", "m1"]);
  });

  it("member self completion key", () => {
    expect(queryKeys.member.kyc()).toEqual(["member", "kyc"]);
  });
});
