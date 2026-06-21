// admin/apps/portal/src/__tests__/tenant-savings/ProductsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { SavingsProductOut } from "@sacco/schemas";

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
  usePathname: () => "/savings",
}));

import { ProductsTable } from "../../../app/(tenant-authed)/savings/_components/ProductsTable";

const product: SavingsProductOut = {
  id: "p1",
  name: "Regular Savings",
  interest_rate: "5.00",
  minimum_balance: "500.00",
  liability_account_id: "g1",
  is_active: true,
};

function renderTable(rows: SavingsProductOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <ProductsTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("ProductsTable", () => {
  it("renders a product row with name and interest", () => {
    renderTable([product]);
    expect(screen.getByText("Regular Savings")).toBeInTheDocument();
    expect(screen.getByText("5.00%")).toBeInTheDocument();
  });

  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No savings products yet")).toBeInTheDocument();
  });
});
