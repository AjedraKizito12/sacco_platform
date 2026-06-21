// admin/apps/portal/src/__tests__/tenant-credit/ProductsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { LoanProductOut } from "@sacco/schemas";

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
  usePathname: () => "/credit",
}));

import { ProductsTable } from "../../../app/(tenant-authed)/credit/_components/ProductsTable";

const product: LoanProductOut = {
  id: "p1",
  name: "Personal Loan",
  description: null,
  interest_method: "reducing_balance",
  annual_interest_rate: "18.50",
  repayment_frequency: "monthly",
  max_term_periods: 24,
  min_amount: "100000.00",
  max_amount: "5000000.00",
  required_approvals: 1,
  disbursement_destinations: ["member_savings"],
  repayment_allocation: "INTEREST_PRINCIPAL",
  gl_principal_receivable_code: "1200",
  gl_interest_receivable_code: "1210",
  gl_interest_income_code: "4100",
  gl_loan_loss_expense_code: "5100",
  penalty_fee_type_code: null,
  write_off_threshold: "0.00",
  is_active: true,
  created_at: "2026-06-21T00:00:00Z",
  updated_at: "2026-06-21T00:00:00Z",
};

function renderTable(rows: LoanProductOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <ProductsTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("ProductsTable", () => {
  it("links the name to detail and renders the interest rate", () => {
    renderTable([product]);
    expect(screen.getByRole("link", { name: "Personal Loan" })).toHaveAttribute(
      "href",
      "/credit/products/p1",
    );
    expect(screen.getByText("18.50%")).toBeInTheDocument();
  });

  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No loan products yet")).toBeInTheDocument();
  });
});
