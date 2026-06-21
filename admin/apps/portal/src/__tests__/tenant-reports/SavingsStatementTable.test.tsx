// admin/apps/portal/src/__tests__/tenant-reports/SavingsStatementTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { SavingsStatementLineOut } from "@sacco/schemas";

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
  usePathname: () => "/reports/savings-statement",
}));

import { SavingsStatementTable } from "../../../app/(tenant-authed)/reports/savings-statement/_components/SavingsStatementTable";

const line: SavingsStatementLineOut = {
  savings_account_id: "s1", member_id: "m1", posted_at: "2026-06-01T00:00:00Z",
  transaction_type: "deposit", narration: null, amount: "5000.00", running_balance: "5000.00",
};

function renderTable(rows: SavingsStatementLineOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <SavingsStatementTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("SavingsStatementTable", () => {
  it("renders a line", () => {
    renderTable([line]);
    expect(screen.getByText("deposit")).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No savings transactions")).toBeInTheDocument();
  });
});
