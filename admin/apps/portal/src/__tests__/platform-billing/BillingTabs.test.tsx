import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

let pathname = "/platform/billing/plans";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

import { BillingTabs } from "../../../app/platform/(authed)/billing/_components/BillingTabs";

describe("BillingTabs", () => {
  it("links to all four billing sections", () => {
    pathname = "/platform/billing/plans";
    render(<BillingTabs />);
    expect(screen.getByRole("link", { name: /plans/i })).toHaveAttribute("href", "/platform/billing/plans");
    expect(screen.getByRole("link", { name: /subscriptions/i })).toHaveAttribute("href", "/platform/billing/subscriptions");
    expect(screen.getByRole("link", { name: /invoices/i })).toHaveAttribute("href", "/platform/billing/invoices");
    expect(screen.getByRole("link", { name: /payments/i })).toHaveAttribute("href", "/platform/billing/payments");
  });

  it("marks the active section with aria-current", () => {
    pathname = "/platform/billing/invoices";
    render(<BillingTabs />);
    expect(screen.getByRole("link", { name: /invoices/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /plans/i })).not.toHaveAttribute("aria-current");
  });
});
