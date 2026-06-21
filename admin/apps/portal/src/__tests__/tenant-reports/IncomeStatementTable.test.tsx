// admin/apps/portal/src/__tests__/tenant-reports/IncomeStatementTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { IncomeStatementLineOut } from "@sacco/schemas";

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
  usePathname: () => "/reports/income-statement",
}));

import { IncomeStatementTable } from "../../../app/(tenant-authed)/reports/income-statement/_components/IncomeStatementTable";

const line: IncomeStatementLineOut = {
  account_id: "a1", account_code: "4000", account_name: "Interest Income",
  account_type: "income", debit_total: "0.00", credit_total: "500.00", net_movement: "500.00",
};

function renderTable(rows: IncomeStatementLineOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <IncomeStatementTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("IncomeStatementTable", () => {
  it("renders a line", () => {
    renderTable([line]);
    expect(screen.getByText("Interest Income")).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No income-statement lines")).toBeInTheDocument();
  });
});
