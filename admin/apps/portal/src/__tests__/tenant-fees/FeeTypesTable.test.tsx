// admin/apps/portal/src/__tests__/tenant-fees/FeeTypesTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { FeeTypeOut } from "@sacco/schemas";

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
  usePathname: () => "/fees/types",
}));

import { FeeTypesTable } from "../../../app/(tenant-authed)/fees/types/_components/FeeTypesTable";

const feeType: FeeTypeOut = {
  id: "f1", code: "annual", name: "Annual Fee", description: null, applicable_to: "member",
  amount_kind: "fixed", amount: "20000.00", percentage_basis: null, percentage_rate: null,
  currency: "UGX", trigger_kind: "schedule", event_name: null, schedule_config: null,
  gl_income_account_code: "4200", gl_receivable_account_code: "1300", is_active: true,
  requires_collection: false,
};

function renderTable(rows: FeeTypeOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <FeeTypesTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("FeeTypesTable", () => {
  it("links the name to detail and renders the code", () => {
    renderTable([feeType]);
    expect(screen.getByRole("link", { name: "Annual Fee" })).toHaveAttribute(
      "href",
      "/fees/types/f1",
    );
    expect(screen.getByText("annual")).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No fee types yet")).toBeInTheDocument();
  });
});
