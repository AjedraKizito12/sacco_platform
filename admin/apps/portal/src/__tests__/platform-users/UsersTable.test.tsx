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
import { describe, expect, it, vi } from "vitest";
import type { PlatformUserOut } from "@sacco/schemas";

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

// Import after vi.mock so the hoisted mock is in place when the module graph loads.
import { UsersTable, sortRows } from "../../../app/platform/(authed)/users/_components/UsersTable";

const rows: PlatformUserOut[] = [
  {
    id: "u1",
    email: "ada@example.com",
    full_name: "Ada Ops",
    is_active: true,
    is_superuser: false,
    role: "admin",
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    last_login_at: "2026-06-10T08:00:00Z",
  },
  {
    id: "u2",
    email: "ben@example.com",
    full_name: "Ben Finance",
    is_active: false,
    is_superuser: false,
    role: "finance",
    created_at: "2026-06-02T00:00:00Z",
    updated_at: "2026-06-02T00:00:00Z",
    last_login_at: null,
  },
];

function renderTable(data: PlatformUserOut[]) {
  return render(<UsersTable rows={data} />);
}

describe("UsersTable", () => {
  it("renders a row per user with email and status", () => {
    renderTable(rows);
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("ben@example.com")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Inactive")).toBeInTheDocument();
    expect(screen.getByText("Never")).toBeInTheDocument();
  });

  it("renders the empty state when there are no users", () => {
    renderTable([]);
    expect(screen.getByText(/no platform users/i)).toBeInTheDocument();
  });
});

describe("sortRows", () => {
  it("sorts ascending by a string column", () => {
    const result = sortRows(rows, "full_name", "asc");
    expect(result.map((r) => r.id)).toEqual(["u1", "u2"]); // "Ada Ops" < "Ben Finance"
  });

  it("sorts descending by reversing the sorted order", () => {
    const result = sortRows(rows, "full_name", "desc");
    expect(result.map((r) => r.id)).toEqual(["u2", "u1"]); // "Ben Finance" > "Ada Ops"
  });

  it("coerces null to empty string and sorts without throwing", () => {
    // u2 has last_login_at: null — treated as "" it sorts before any real date string
    const result = sortRows(rows, "last_login_at", "asc");
    expect(result[0]?.id).toBe("u2"); // null → "" comes first
    expect(result[1]?.id).toBe("u1");
  });

  it("returns the original order when column is null", () => {
    const result = sortRows(rows, null, "asc");
    expect(result.map((r) => r.id)).toEqual(["u1", "u2"]);
  });
});
