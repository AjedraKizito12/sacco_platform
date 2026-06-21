// admin/apps/portal/src/__tests__/tenant-reports/RunsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { ReportRunOut } from "@sacco/schemas";

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
  usePathname: () => "/reports/runs",
}));

import { RunsTable } from "../../../app/(tenant-authed)/reports/runs/_components/RunsTable";

const run: ReportRunOut = {
  id: "r1", report_type: "trial_balance", as_of_date: "2026-06-01", status: "done",
  started_at: "2026-06-01T00:00:00Z", completed_at: "2026-06-01T00:05:00Z", error_detail: null,
};

function renderTable(rows: ReportRunOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <RunsTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("RunsTable", () => {
  it("renders a run with its status badge", () => {
    renderTable([run]);
    expect(screen.getByText("trial_balance")).toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No report runs yet")).toBeInTheDocument();
  });
});
