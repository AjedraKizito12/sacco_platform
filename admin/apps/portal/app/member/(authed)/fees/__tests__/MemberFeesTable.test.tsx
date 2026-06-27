import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { TenantCurrencyProvider } from "@sacco/ui";

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
  usePathname: () => "/member/fees",
}));

import { MemberFeesTable } from "../_components/MemberFeesTable";

describe("MemberFeesTable", () => {
  it("renders a fee row", () => {
    render(
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <MemberFeesTable
          rows={[{ id: "f1", amount: "10000.00", status: "assessed" }]}
        />
      </TenantCurrencyProvider>,
    );
    expect(screen.getByText("Assessed")).toBeInTheDocument();
  });
});
