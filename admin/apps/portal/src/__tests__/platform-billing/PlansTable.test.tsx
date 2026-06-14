/**
 * nuqs is a dependency of @sacco/ui, not of @sacco/portal.  With pnpm
 * strict isolation (shamefully-hoist=false) the test runner cannot
 * resolve "nuqs/adapters/testing" from the portal app's module graph, so
 * NuqsTestingAdapter is genuinely unavailable here.  Instead we mock
 * useTableUrlState (the @sacco/ui hook that internally calls useQueryStates)
 * to return a fixed TableUrlState — matching the pattern used in UsersTable.test.tsx.
 */
// admin/apps/portal/src/__tests__/platform-billing/PlansTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SubscriptionPlanOut } from "@sacco/schemas";

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
  usePathname: () => "/platform/billing/plans",
}));

// Import after vi.mock so the hoisted mock is in place when the module graph loads.
import { TenantCurrencyProvider } from "@sacco/ui";
import { PlansTable } from "../../../app/platform/(authed)/billing/plans/_components/PlansTable";

function plan(over: Partial<SubscriptionPlanOut>): SubscriptionPlanOut {
  return {
    id: "p1", code: "starter", name: "Starter", description: null, currency: "UGX",
    base_price: "50000", per_user_price: "0", per_member_price: "0",
    billing_period: "monthly", member_limit: null, user_limit: null, features: {},
    trial_period_days: 0, grace_period_days: 30, is_active: true,
    created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    ...over,
  };
}

describe("PlansTable", () => {
  it("renders plan rows with a linked name and formatted price", () => {
    render(
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <PlansTable rows={[plan({ id: "p1", name: "Starter", base_price: "50000" })]} />
      </TenantCurrencyProvider>,
    );
    const link = screen.getByRole("link", { name: /starter/i });
    expect(link).toHaveAttribute("href", "/platform/billing/plans/p1");
    expect(screen.getByText(/50,000/)).toBeInTheDocument();
  });

  it("renders the empty state with no rows", () => {
    render(
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <PlansTable rows={[]} />
      </TenantCurrencyProvider>,
    );
    expect(screen.getByText(/no plans/i)).toBeInTheDocument();
  });
});
