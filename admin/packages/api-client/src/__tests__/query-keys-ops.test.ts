import { describe, expect, it } from "vitest";
import { queryKeys } from "../query-keys";

describe("ops query keys", () => {
  it("nest under a common root", () => {
    expect(queryKeys.ops.root()).toEqual(["ops"]);
    expect(queryKeys.ops.backups()).toEqual(["ops", "backups"]);
    expect(queryKeys.ops.lastVerified()).toEqual(["ops", "lastVerified"]);
  });
});
