// admin/apps/portal/src/__tests__/tenant-credit/RestructuringsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { RestructuringOut } from "@sacco/schemas";

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

import { RestructuringsTable } from "../../../app/(tenant-authed)/credit/loans/[id]/_components/RestructuringsTable";

const row: RestructuringOut = {
  id: "rs1", loan_id: "l1", restructuring_type: "term_extension", periods_added: 3,
  new_term_periods: 15, new_maturity_date: "2027-09-01", reason: "x",
  executed_at: "2026-06-21T00:00:00Z",
};

function renderTable(rows: RestructuringOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <RestructuringsTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("RestructuringsTable", () => {
  it("renders a restructuring row", () => {
    renderTable([row]);
    expect(screen.getByText("term_extension")).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No restructurings yet")).toBeInTheDocument();
  });
});
