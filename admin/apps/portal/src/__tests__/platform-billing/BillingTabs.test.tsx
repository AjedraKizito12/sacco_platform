// admin/apps/portal/src/__tests__/platform-billing/BillingTabs.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

let pathname = "/platform/billing/plans";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

import { BillingTabs } from "../../../app/platform/(authed)/billing/_components/BillingTabs";

describe("BillingTabs", () => {
  it("links to plans and subscriptions", () => {
    pathname = "/platform/billing/plans";
    render(<BillingTabs />);
    expect(screen.getByRole("link", { name: /plans/i })).toHaveAttribute(
      "href",
      "/platform/billing/plans",
    );
    expect(screen.getByRole("link", { name: /subscriptions/i })).toHaveAttribute(
      "href",
      "/platform/billing/subscriptions",
    );
  });

  it("marks the active section with aria-current", () => {
    pathname = "/platform/billing/subscriptions";
    render(<BillingTabs />);
    expect(screen.getByRole("link", { name: /subscriptions/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: /plans/i })).not.toHaveAttribute(
      "aria-current",
    );
  });
});
