import { describe, expect, it } from "vitest";
import { queryKeys } from "../query-keys";

describe("search query keys", () => {
  it("scoped by audience + query", () => {
    expect(queryKeys.search.root()).toEqual(["search"]);
    expect(queryKeys.search.platform("ab")).toEqual(["search", "platform", "ab"]);
    expect(queryKeys.search.tenant("ab")).toEqual(["search", "tenant", "ab"]);
  });
});
