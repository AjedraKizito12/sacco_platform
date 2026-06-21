// admin/apps/portal/src/__tests__/tenant-shares/AccountsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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
  usePathname: () => "/shares/accounts",
}));

import {
  AccountsTable,
  type AccountRow,
} from "../../../app/(tenant-authed)/shares/accounts/_components/AccountsTable";

const row: AccountRow = {
  id: "a1",
  member_label: "Ada Loan (M-0001)",
  product_name: "Ordinary Shares",
  shares_held: 5,
  total_value: "5000.00",
};

function renderTable(rows: AccountRow[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <AccountsTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("AccountsTable", () => {
  it("links the member label to the account detail", () => {
    renderTable([row]);
    expect(screen.getByRole("link", { name: "Ada Loan (M-0001)" })).toHaveAttribute(
      "href",
      "/shares/accounts/a1",
    );
    expect(screen.getByText("Ordinary Shares")).toBeInTheDocument();
  });

  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No share accounts yet")).toBeInTheDocument();
  });
});
