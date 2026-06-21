// admin/apps/portal/src/__tests__/tenant-credit/ApplicationsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";

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
  usePathname: () => "/credit/applications",
}));

import {
  ApplicationsTable,
  type ApplicationRow,
} from "../../../app/(tenant-authed)/credit/applications/_components/ApplicationsTable";

const row: ApplicationRow = {
  id: "a1",
  member_label: "Ada Loan (M-0001)",
  product_name: "Personal Loan",
  requested_amount: "1000000.00",
  requested_term_periods: 12,
  status: "pending",
};

function renderTable(rows: ApplicationRow[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <ApplicationsTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("ApplicationsTable", () => {
  it("links the member label to detail and renders the status badge", () => {
    renderTable([row]);
    expect(screen.getByRole("link", { name: "Ada Loan (M-0001)" })).toHaveAttribute(
      "href",
      "/credit/applications/a1",
    );
    expect(screen.getByText("Personal Loan")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No loan applications yet")).toBeInTheDocument();
  });
});
