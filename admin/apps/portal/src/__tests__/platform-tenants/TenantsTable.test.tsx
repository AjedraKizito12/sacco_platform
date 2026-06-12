/**
 * nuqs is a dependency of @sacco/ui, not of @sacco/portal.  With pnpm
 * strict isolation (shamefully-hoist=false) the test runner cannot
 * resolve "nuqs/adapters/testing" from the portal app's module graph, so
 * NuqsTestingAdapter is genuinely unavailable here.  Instead we mock
 * useTableUrlState (the @sacco/ui hook that internally calls useQueryStates)
 * to return a fixed TableUrlState — matching the pattern used in
 * admin/packages/ui/src/components/DataTable/DataTable.stories.tsx where
 * mockUrlState() provides a static state object for story render fns.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { TenantOut } from "@sacco/schemas";

// nuqs is a dep of @sacco/ui, not the portal (pnpm isolation) — mock the
// url-state hook like UsersTable.test.tsx does, keeping everything else real.
const mockUrlState = {
  page: 1,
  pageSize: 25,
  sortColumn: null as string | null,
  sortDirection: "asc" as const,
  filters: {} as Record<string, string>,
  density: "default" as const,
  setPage: vi.fn(),
  setPageSize: vi.fn(),
  setSort: vi.fn(),
  setFilter: vi.fn(),
  setFilters: vi.fn(),
  setDensity: vi.fn(),
  reset: vi.fn(),
};
vi.mock("@sacco/ui", async (importActual) => {
  const actual = await importActual<typeof import("@sacco/ui")>();
  return { ...actual, useTableUrlState: () => mockUrlState };
});

import { filterTenants, sortTenants, TenantsTable } from "../../../app/platform/(authed)/tenants/_components/TenantsTable";

function tenant(over: Partial<TenantOut>): TenantOut {
  return {
    id: "t1", slug: "alpha", schema_name: "tenant_alpha", name: "Alpha SACCO",
    status: "active", is_active: true, provisioning_state: null,
    failed_step: null, failure_reason: null,
    provisioning_started_at: null, provisioning_completed_at: "2026-06-01T00:00:00Z",
    seed_version: 1, created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    ...over,
  };
}

const rows = [
  tenant({ id: "t1", slug: "alpha", name: "Alpha SACCO", status: "active" }),
  tenant({ id: "t2", slug: "beta", name: "Beta SACCO", status: "failed" }),
];

describe("TenantsTable", () => {
  beforeEach(() => {
    mockUrlState.filters = {};
  });

  it("renders a row per tenant with name link and status badge", () => {
    render(<TenantsTable rows={rows} />);
    expect(screen.getByRole("link", { name: "Alpha SACCO" })).toHaveAttribute(
      "href",
      "/platform/tenants/t1",
    );
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("renders the empty state when there are no tenants", () => {
    render(<TenantsTable rows={[]} />);
    expect(screen.getByText(/no tenants/i)).toBeInTheDocument();
  });

  it("filters by status when the f_status filter is set", () => {
    mockUrlState.filters = { status: "failed" };
    render(<TenantsTable rows={rows} />);
    expect(screen.queryByText("Alpha SACCO")).toBeNull();
    expect(screen.getByText("Beta SACCO")).toBeInTheDocument();
  });
});

describe("filterTenants", () => {
  it("returns all rows when no status filter", () => {
    expect(filterTenants(rows, undefined)).toHaveLength(2);
  });
  it("returns only matching rows for a status", () => {
    expect(filterTenants(rows, "failed").map((t) => t.id)).toEqual(["t2"]);
  });
});

describe("sortTenants", () => {
  it("sorts ascending by name", () => {
    const result = sortTenants(rows, "name", "asc");
    expect(result.map((t) => t.name)).toEqual(["Alpha SACCO", "Beta SACCO"]);
  });

  it("sorts descending by name (reverses order)", () => {
    const result = sortTenants(rows, "name", "desc");
    expect(result.map((t) => t.name)).toEqual(["Beta SACCO", "Alpha SACCO"]);
  });

  it("returns rows unchanged when column is null", () => {
    const result = sortTenants(rows, null, "asc");
    expect(result.map((t) => t.id)).toEqual(["t1", "t2"]);
  });
});
