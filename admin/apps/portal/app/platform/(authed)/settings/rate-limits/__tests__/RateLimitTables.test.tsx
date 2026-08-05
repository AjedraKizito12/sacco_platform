import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type {
  RateLimitOverrideRow,
  RateLimitPolicyOut,
} from "@sacco/schemas";
import { flattenRateLimitOverrides } from "@sacco/schemas";

vi.mock("@sacco/ui", async (importActual) => {
  const actual = await importActual<typeof import("@sacco/ui")>();
  return {
    ...actual,
    useTableUrlState: vi.fn().mockReturnValue({
      page: 1,
      pageSize: 25,
      sortColumn: "name",
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
  usePathname: () => "/platform/settings/rate-limits",
}));

import { PolicyTable } from "../_components/PolicyTable";
import { OverridesTable } from "../_components/OverridesTable";

const POLICIES: RateLimitPolicyOut[] = [
  { name: "auth_login", limit: 10, window_seconds: 60 },
  { name: "authenticated_default", limit: 300, window_seconds: 60 },
];

describe("flattenRateLimitOverrides", () => {
  it("flattens plan × policy overrides into stable-id rows", () => {
    const rows = flattenRateLimitOverrides({
      growth: { authenticated_default: { limit: 1000 } },
      pro: { reporting: { window_seconds: 30 } },
    });
    expect(rows).toContainEqual({
      id: "growth:authenticated_default",
      plan: "growth",
      policy: "authenticated_default",
      limit: 1000,
      window_seconds: null,
    });
    expect(rows).toContainEqual({
      id: "pro:reporting",
      plan: "pro",
      policy: "reporting",
      limit: null,
      window_seconds: 30,
    });
  });
});

describe("PolicyTable", () => {
  it("renders each policy with its limit and window", () => {
    render(<PolicyTable policies={POLICIES} />);
    expect(screen.getByText("auth_login")).toBeInTheDocument();
    expect(screen.getByText("authenticated_default")).toBeInTheDocument();
    expect(screen.getByText("300")).toBeInTheDocument();
    expect(screen.getAllByText("60s").length).toBeGreaterThan(0);
  });
});

describe("OverridesTable", () => {
  it("renders override rows with an em-dash for absent fields", () => {
    const rows: RateLimitOverrideRow[] = [
      {
        id: "growth:authenticated_default",
        plan: "growth",
        policy: "authenticated_default",
        limit: 1000,
        window_seconds: null,
      },
    ];
    render(<OverridesTable rows={rows} />);
    expect(screen.getByText("growth")).toBeInTheDocument();
    expect(screen.getByText("1,000")).toBeInTheDocument();
  });

  it("shows the empty state when no plan overrides exist", () => {
    render(<OverridesTable rows={[]} />);
    expect(screen.getByText(/no plan overrides/i)).toBeInTheDocument();
  });
});
