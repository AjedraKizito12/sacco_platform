import { describe, expect, it } from "vitest";
import { queryKeys } from "../query-keys";

describe("notifications query keys", () => {
  it("feed and preferences keys are scoped by audience under a common root", () => {
    expect(queryKeys.notifications.root()).toEqual(["notifications"]);
    expect(queryKeys.notifications.feed("platform")).toEqual([
      "notifications",
      "feed",
      "platform",
    ]);
    expect(queryKeys.notifications.feed("member")).toEqual([
      "notifications",
      "feed",
      "member",
    ]);
    expect(queryKeys.notifications.preferences("tenant")).toEqual([
      "notifications",
      "preferences",
      "tenant",
    ]);
  });

  it("admin template and event keys are stable", () => {
    expect(queryKeys.notifications.templates()).toEqual([
      "notifications",
      "templates",
    ]);
    expect(queryKeys.notifications.events()).toEqual([
      "notifications",
      "events",
      {},
    ]);
    expect(queryKeys.notifications.events({ status: "failed" })).toEqual([
      "notifications",
      "events",
      { status: "failed" },
    ]);
  });
});
