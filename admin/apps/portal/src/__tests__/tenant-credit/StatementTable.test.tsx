// admin/apps/portal/src/__tests__/tenant-credit/StatementTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { StatementLineOut } from "@sacco/schemas";

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

import { StatementTable } from "../../../app/(tenant-authed)/credit/loans/[id]/_components/StatementTable";

const line: StatementLineOut = {
  date: "2026-06-21", line_type: "disbursement", description: "Disbursed",
  debit: "1000000.00", credit: "0.00", running_balance: "1000000.00",
};

function renderTable(rows: StatementLineOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <StatementTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("StatementTable", () => {
  it("renders a statement line", () => {
    renderTable([line]);
    expect(screen.getByText("Disbursed")).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No statement lines yet")).toBeInTheDocument();
  });
});
