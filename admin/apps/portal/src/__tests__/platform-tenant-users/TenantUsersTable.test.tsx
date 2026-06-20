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

import { TenantUsersTable } from "../../../app/platform/(authed)/tenants/[id]/users/_components/TenantUsersTable";
import type { TenantUserOut } from "@sacco/schemas";

const rows: TenantUserOut[] = [
  {
    id: "u1",
    email: "ada@sacco.test",
    full_name: "Ada Loan",
    is_active: true,
    is_admin: true,
    last_login_at: null,
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    impersonation_id: null,
  },
];

describe("TenantUsersTable", () => {
  it("renders email link, role label, and status badge", () => {
    render(<TenantUsersTable rows={rows} tenantId="t1" />);
    expect(screen.getByRole("link", { name: "ada@sacco.test" })).toHaveAttribute(
      "href",
      "/platform/tenants/t1/users/u1",
    );
    expect(screen.getByText("Admin")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("shows the empty state", () => {
    render(<TenantUsersTable rows={[]} tenantId="t1" />);
    expect(screen.getByText("No users yet")).toBeInTheDocument();
  });
});
