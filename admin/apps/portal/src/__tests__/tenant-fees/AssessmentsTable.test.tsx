// admin/apps/portal/src/__tests__/tenant-fees/AssessmentsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";

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
  usePathname: () => "/fees/assessments",
}));

import {
  AssessmentsTable,
  type AssessmentRow,
} from "../../../app/(tenant-authed)/fees/assessments/_components/AssessmentsTable";

const row: AssessmentRow = {
  id: "a1",
  fee_type_name: "Annual Fee",
  target_type: "member",
  amount: "20000.00",
  period_start: "2026-06-01",
  status: "assessed",
};

function renderTable(rows: AssessmentRow[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <AssessmentsTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("AssessmentsTable", () => {
  it("links the fee type to detail and renders the status badge", () => {
    renderTable([row]);
    expect(screen.getByRole("link", { name: "Annual Fee" })).toHaveAttribute(
      "href",
      "/fees/assessments/a1",
    );
    expect(screen.getByText("Assessed")).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No assessments yet")).toBeInTheDocument();
  });
});
