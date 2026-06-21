// admin/apps/portal/src/__tests__/tenant-reports/FeeCollectionTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { FeeCollectionRowOut } from "@sacco/schemas";

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
  usePathname: () => "/reports/fee-collection",
}));

import { FeeCollectionTable } from "../../../app/(tenant-authed)/reports/fee-collection/_components/FeeCollectionTable";

const row: FeeCollectionRowOut = {
  fee_type_id: "f1", fee_type_name: "Annual Fee", target_type: "member",
  assessed_total: "100000.00", collected_total: "60000.00",
  outstanding_total: "40000.00", waived_total: "0.00",
};

function renderTable(rows: FeeCollectionRowOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <FeeCollectionTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("FeeCollectionTable", () => {
  it("renders a row", () => {
    renderTable([row]);
    expect(screen.getByText("Annual Fee")).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No fee-collection data")).toBeInTheDocument();
  });
});
