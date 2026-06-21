// admin/apps/portal/src/__tests__/tenant-credit/RepaymentsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { LoanRepaymentOut } from "@sacco/schemas";

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
  usePathname: () => "/credit/loans/l1",
}));

import { RepaymentsTable } from "../../../app/(tenant-authed)/credit/loans/[id]/_components/RepaymentsTable";

const rep: LoanRepaymentOut = {
  id: "r1", loan_id: "l1", amount: "95000.00", principal_applied: "80000.00",
  interest_applied: "15000.00", penalties_applied: "0.00", overpayment: "0.00",
  payment_account_id: "g1", journal_entry_id: "j1", posted_by: "u1",
  narration: null, idempotency_key: "k", created_at: "2026-06-21T00:00:00Z",
};

function renderTable(rows: LoanRepaymentOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <RepaymentsTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("RepaymentsTable", () => {
  it("renders a repayment row amount", () => {
    const { container } = renderTable([rep]);
    expect(container.querySelector('[data-amount="95000.00"]')).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No repayments yet")).toBeInTheDocument();
  });
});
