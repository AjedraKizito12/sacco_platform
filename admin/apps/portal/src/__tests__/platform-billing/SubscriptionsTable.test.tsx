/**
 * nuqs is a dependency of @sacco/ui, not of @sacco/portal. With pnpm
 * strict isolation (shamefully-hoist=false) the test runner cannot
 * resolve "nuqs/adapters/testing" from the portal app's module graph, so
 * NuqsTestingAdapter is genuinely unavailable here. Instead we mock
 * useTableUrlState (the @sacco/ui hook that internally calls useQueryStates)
 * to return a fixed TableUrlState — matching the pattern used in PlansTable.test.tsx.
 */
// admin/apps/portal/src/__tests__/platform-billing/SubscriptionsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@sacco/ui", async (importActual) => {
  const actual = await importActual<typeof import("@sacco/ui")>();
  return {
    ...actual,
    useTableUrlState: vi.fn().mockReturnValue({
      page: 1,
      pageSize: 25,
      sortColumn: null,
      sortDirection: "asc" as const,
      filters: {},
      density: "default" as const,
      setPage: vi.fn(),
      setPageSize: vi.fn(),
      setSort: vi.fn(),
      setFilter: vi.fn(),
      setFilters: vi.fn(),
      setDensity: vi.fn(),
      reset: vi.fn(),
    }),
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/platform/billing/subscriptions",
}));

import {
  SubscriptionsTable,
  type SubscriptionRow,
} from "../../../app/platform/(authed)/billing/subscriptions/_components/SubscriptionsTable";

const row: SubscriptionRow = {
  id: "s1", tenant_id: "t1", tenant_name: "Alpha SACCO", plan_id: "p1",
  plan_name: "Starter", status: "active",
  current_period_start: "2026-06-01", current_period_end: "2026-06-30",
  next_billing_date: "2026-07-01",
};

describe("SubscriptionsTable", () => {
  it("renders the tenant link, plan name and status badge", () => {
    render(<SubscriptionsTable rows={[row]} />);
    expect(screen.getByRole("link", { name: /alpha sacco/i })).toHaveAttribute(
      "href",
      "/platform/billing/subscriptions/s1",
    );
    expect(screen.getByText("Starter")).toBeInTheDocument();
    expect(screen.getByText(/active/i)).toBeInTheDocument();
  });

  it("renders the empty state with no rows", () => {
    render(<SubscriptionsTable rows={[]} />);
    expect(screen.getByText(/no subscriptions/i)).toBeInTheDocument();
  });
});
