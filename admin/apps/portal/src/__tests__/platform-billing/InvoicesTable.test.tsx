/**
 * nuqs is a dependency of @sacco/ui, not of @sacco/portal. With pnpm
 * strict isolation (shamefully-hoist=false) the test runner cannot
 * resolve "nuqs/adapters/testing" from the portal app's module graph, so
 * NuqsTestingAdapter is genuinely unavailable here. Instead we mock
 * useTableUrlState (the @sacco/ui hook that internally calls useQueryStates)
 * to return a fixed TableUrlState — matching the pattern used in
 * SubscriptionsTable.test.tsx.
 */
// admin/apps/portal/src/__tests__/platform-billing/InvoicesTable.test.tsx
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
  usePathname: () => "/platform/billing/invoices",
}));

import {
  InvoicesTable,
  type InvoiceRow,
} from "../../../app/platform/(authed)/billing/invoices/_components/InvoicesTable";

const row: InvoiceRow = {
  id: "i1", invoice_number: "INV-2026-000001", tenant_id: "t1",
  tenant_name: "Alpha SACCO", amount_total: "120000", amount_paid: "0",
  currency: "UGX", status: "issued", due_at: "2026-07-01",
};

function renderTable(rows: InvoiceRow[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <InvoicesTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("InvoicesTable", () => {
  it("renders an invoice row with a linked number, tenant and total", () => {
    renderTable([row]);
    expect(screen.getByRole("link", { name: /INV-2026-000001/i })).toHaveAttribute(
      "href",
      "/platform/billing/invoices/i1",
    );
    expect(screen.getByText(/alpha sacco/i)).toBeInTheDocument();
    expect(screen.getByText(/120,000/)).toBeInTheDocument();
  });

  it("renders the empty state with no rows", () => {
    renderTable([]);
    expect(screen.getByText(/no invoices/i)).toBeInTheDocument();
  });
});
