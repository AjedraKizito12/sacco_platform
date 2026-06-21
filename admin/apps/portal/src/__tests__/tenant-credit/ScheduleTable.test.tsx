// admin/apps/portal/src/__tests__/tenant-credit/ScheduleTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { LoanInstallmentOut } from "@sacco/schemas";

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

import { ScheduleTable } from "../../../app/(tenant-authed)/credit/loans/[id]/_components/ScheduleTable";

const inst: LoanInstallmentOut = {
  id: "i1", loan_id: "l1", period_number: 1, due_date: "2026-07-01",
  principal_due: "80000.00", interest_due: "15000.00", total_due: "95000.00",
  principal_paid: "0.00", interest_paid: "0.00", status: "pending", paid_at: null,
};

function renderTable(rows: LoanInstallmentOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <ScheduleTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("ScheduleTable", () => {
  it("renders an installment row", () => {
    renderTable([inst]);
    expect(screen.getByText("pending")).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No schedule yet")).toBeInTheDocument();
  });
});
