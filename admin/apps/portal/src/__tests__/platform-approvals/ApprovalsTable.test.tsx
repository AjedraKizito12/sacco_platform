/**
 * nuqs is a dependency of @sacco/ui, not of @sacco/portal. With pnpm strict
 * isolation the test runner cannot resolve nuqs's testing adapter from the
 * portal app's module graph, so we mock useTableUrlState to return a fixed
 * TableUrlState — matching the pattern used in InvoicesTable.test.tsx.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

import {
  ApprovalsTable,
  type ApprovalRow,
} from "../../../app/platform/(authed)/approvals/_components/ApprovalsTable";

const rows: ApprovalRow[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    operation_type: "billing.void_invoice",
    operation_label: "Void invoice",
    status: "pending",
    current_approvals: 0,
    required_approvals: 1,
    requested_by_label: "maker@platform.test",
    requested_at: "2026-06-16T10:00:00Z",
  },
];

describe("ApprovalsTable", () => {
  it("renders the operation label as a link to the detail page", () => {
    render(<ApprovalsTable rows={rows} />);
    const link = screen.getByRole("link", { name: "Void invoice" });
    expect(link).toHaveAttribute(
      "href",
      "/platform/approvals/11111111-1111-1111-1111-111111111111",
    );
  });

  it("renders the quorum as '{current} of {required}'", () => {
    render(<ApprovalsTable rows={rows} />);
    expect(screen.getByText("0 of 1")).toBeInTheDocument();
  });

  it("renders the resolved requester label", () => {
    render(<ApprovalsTable rows={rows} />);
    expect(screen.getByText("maker@platform.test")).toBeInTheDocument();
  });

  it("shows the empty state when there are no rows", () => {
    render(<ApprovalsTable rows={[]} />);
    expect(screen.getByText("No approval requests")).toBeInTheDocument();
  });
});
