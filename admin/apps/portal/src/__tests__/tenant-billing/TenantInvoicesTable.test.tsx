// admin/apps/portal/src/__tests__/tenant-billing/TenantInvoicesTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";

// nuqs has no resolvable test adapter under pnpm strict isolation, so mock the
// @sacco/ui useTableUrlState hook (matches InvoicesTable / SubscriptionsTable).
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
  usePathname: () => "/billing",
}));

import {
  TenantInvoicesTable,
  type TenantInvoiceRow,
} from "../../../app/(tenant-authed)/billing/_components/TenantInvoicesTable";

const row: TenantInvoiceRow = {
  id: "i1", invoice_number: "INV-2026-000001", amount_total: "120000",
  currency: "UGX", status: "issued", due_at: "2026-07-01",
};

function renderTable(rows: TenantInvoiceRow[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <TenantInvoicesTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("TenantInvoicesTable", () => {
  it("links the invoice number to the tenant invoice detail", () => {
    renderTable([row]);
    expect(screen.getByRole("link", { name: /INV-2026-000001/i })).toHaveAttribute(
      "href",
      "/billing/invoices/i1",
    );
    expect(screen.getByText(/120,000/)).toBeInTheDocument();
  });

  it("renders the empty state with no rows", () => {
    renderTable([]);
    expect(screen.getByText(/no invoices/i)).toBeInTheDocument();
  });
});
