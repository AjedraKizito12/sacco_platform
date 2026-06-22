// admin/apps/portal/src/__tests__/tenant-ledger/AccountsTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { AccountOut } from "@sacco/schemas";

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
  usePathname: () => "/ledger/accounts",
}));

import { AccountsTable } from "../../../app/(tenant-authed)/ledger/accounts/_components/AccountsTable";

const acct: AccountOut = {
  id: "a1", code: "1000", name: "Cash", account_type: "asset", parent_id: null,
  is_active: true, description: null, created_at: "t", updated_at: "t",
};

function renderTable(rows: AccountOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <AccountsTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("AccountsTable", () => {
  it("links the code to detail and renders the name", () => {
    renderTable([acct]);
    expect(screen.getByRole("link", { name: "1000" })).toHaveAttribute("href", "/ledger/accounts/a1");
    expect(screen.getByText("Cash")).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No accounts yet")).toBeInTheDocument();
  });
});
