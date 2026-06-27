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
  usePathname: () => "/member/savings",
}));

import { MemberSavingsTable } from "../_components/MemberSavingsTable";

describe("MemberSavingsTable", () => {
  it("renders a row per account, linking to detail", () => {
    render(
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <MemberSavingsTable
          rows={[
            {
              id: "a1",
              product_name: "Regular",
              available_balance: "1000.00",
              balance: "1000.00",
            },
          ]}
        />
      </TenantCurrencyProvider>,
    );
    expect(screen.getByRole("link", { name: "Regular" })).toHaveAttribute(
      "href",
      "/member/savings/a1",
    );
  });
});
