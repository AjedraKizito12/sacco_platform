// admin/apps/portal/src/__tests__/tenant-shares/ProductsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { ShareProductOut } from "@sacco/schemas";

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
  usePathname: () => "/shares",
}));

import { ProductsTable } from "../../../app/(tenant-authed)/shares/_components/ProductsTable";

const product: ShareProductOut = {
  id: "p1",
  name: "Ordinary Shares",
  par_value: "1000.00",
  minimum_shares: 1,
  maximum_shares: null,
  share_capital_account_id: "g1",
  is_active: true,
};

function renderTable(rows: ShareProductOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <ProductsTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("ProductsTable", () => {
  it("renders a product row with name and min shares", () => {
    const { container } = renderTable([product]);
    expect(screen.getByText("Ordinary Shares")).toBeInTheDocument();
    expect(container.querySelector('[data-value="1"]')).toBeInTheDocument();
  });

  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No share products yet")).toBeInTheDocument();
  });
});
