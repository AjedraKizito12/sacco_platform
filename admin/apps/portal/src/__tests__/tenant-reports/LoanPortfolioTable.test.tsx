// admin/apps/portal/src/__tests__/tenant-reports/LoanPortfolioTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { LoanPortfolioRowOut } from "@sacco/schemas";

vi.mock("@sacco/ui", async (importActual) => {
  const actual = await importActual<typeof import("@sacco/ui")>();
  return {
    ...actual,
    useTableUrlState: vi.fn().mockReturnValue({
      page: 1, pageSize: 25, sortColumn: null, sortDirection: "asc" as const,
      filters: {}, density: "default" as const, setPage: vi.fn(), setPageSize: vi.fn(),
      setSort: vi.fn(), setFilter: vi.fn(), setFilters: vi.fn(), setDensity: vi.fn(), reset: vi.fn(),
    }),
  };
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/reports/loan-portfolio",
}));

import { LoanPortfolioTable } from "../../../app/(tenant-authed)/reports/loan-portfolio/_components/LoanPortfolioTable";

const row: LoanPortfolioRowOut = {
  loan_id: "l1", loan_reference: "LN-1", member_id: "m1", product_name: "Personal",
  disbursed_at: "2026-01-01", maturity_date: null, status: "disbursed",
  outstanding_principal: "900.00", accrued_interest: "0.00", total_written_off: "0.00",
  days_in_arrears: 0, aging_bucket: "current",
};

function renderTable(rows: LoanPortfolioRowOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <LoanPortfolioTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("LoanPortfolioTable", () => {
  it("renders a row with the loan status badge", () => {
    renderTable([row]);
    expect(screen.getByText("LN-1")).toBeInTheDocument();
    expect(screen.getByText("Disbursed")).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No loans in the portfolio")).toBeInTheDocument();
  });
});
