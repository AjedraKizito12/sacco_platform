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
  usePathname: () => "/member/shares",
}));

import { MemberSharesTable } from "../_components/MemberSharesTable";

describe("MemberSharesTable", () => {
  it("renders a row per share account", () => {
    render(
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <MemberSharesTable
          rows={[
            {
              id: "s1",
              product_name: "Ordinary",
              shares_held: 120,
              total_value: "1200.00",
            },
          ]}
        />
      </TenantCurrencyProvider>,
    );
    expect(screen.getByText("Ordinary")).toBeInTheDocument();
  });
});
