// admin/apps/portal/src/__tests__/tenant-reports/TrialBalanceTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { TrialBalanceLineOut } from "@sacco/schemas";

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
  usePathname: () => "/reports/trial-balance",
}));

import { TrialBalanceTable } from "../../../app/(tenant-authed)/reports/trial-balance/_components/TrialBalanceTable";

const line: TrialBalanceLineOut = {
  account_id: "a1", account_code: "1000", account_name: "Cash", account_type: "asset",
  debit_total: "100.00", credit_total: "0.00", balance: "100.00",
};

function renderTable(rows: TrialBalanceLineOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <TrialBalanceTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("TrialBalanceTable", () => {
  it("renders a line", () => {
    renderTable([line]);
    expect(screen.getByText("Cash")).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No trial-balance lines")).toBeInTheDocument();
  });
});
