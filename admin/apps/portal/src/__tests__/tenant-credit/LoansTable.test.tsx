// admin/apps/portal/src/__tests__/tenant-credit/LoansTable.test.tsx
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
  usePathname: () => "/credit/loans",
}));

import { LoansTable, type LoanRow } from "../../../app/(tenant-authed)/credit/loans/_components/LoansTable";

const row: LoanRow = {
  id: "l1",
  loan_reference: "LN-202606-000001",
  member_label: "Ada Loan (M-0001)",
  principal_amount: "1000000.00",
  outstanding_principal: "900000.00",
  status: "disbursed",
};

function renderTable(rows: LoanRow[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <LoansTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("LoansTable", () => {
  it("links the reference to detail and renders the status badge", () => {
    renderTable([row]);
    expect(screen.getByRole("link", { name: "LN-202606-000001" })).toHaveAttribute(
      "href",
      "/credit/loans/l1",
    );
    expect(screen.getByText("Ada Loan (M-0001)")).toBeInTheDocument();
    expect(screen.getByText("Disbursed")).toBeInTheDocument();
  });

  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No loans yet")).toBeInTheDocument();
  });
});
