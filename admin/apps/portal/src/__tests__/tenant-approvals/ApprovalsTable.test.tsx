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
      sortColumn: "requested_at",
      sortDirection: "desc" as const,
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
  usePathname: () => "/approvals",
}));

import {
  ApprovalsTable,
  type ApprovalRow,
} from "../../../app/(tenant-authed)/approvals/_components/ApprovalsTable";

const ROW: ApprovalRow = {
  id: "550e8400-e29b-41d4-a716-446655440000",
  operation_type: "credit.write_off",
  operation_label: "Write off loan",
  status: "pending",
  current_approvals: 1,
  required_approvals: 2,
  requested_by_label: "you",
  requested_at: "2026-06-22T10:00:00Z",
};

function renderTable(rows: ApprovalRow[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <ApprovalsTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("ApprovalsTable", () => {
  it("links the operation to the detail page and shows the quorum", () => {
    renderTable([ROW]);
    const link = screen.getByRole("link", { name: "Write off loan" });
    expect(link).toHaveAttribute("href", "/approvals/550e8400-e29b-41d4-a716-446655440000");
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
  });

  it("renders the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No approval requests")).toBeInTheDocument();
  });
});
