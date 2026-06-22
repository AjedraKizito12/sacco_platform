// admin/apps/portal/src/__tests__/tenant-ledger/LinesTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { JournalLineOut } from "@sacco/schemas";

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
  usePathname: () => "/ledger/journal-entries/e1",
}));

import { LinesTable } from "../../../app/(tenant-authed)/ledger/journal-entries/[id]/_components/LinesTable";

const line: JournalLineOut = {
  id: "l1", account_id: "a1", debit_amount: "100.0000", credit_amount: "0.0000", description: null,
};

function renderTable(rows: JournalLineOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <LinesTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("LinesTable", () => {
  it("renders the debit amount", () => {
    const { container } = renderTable([line]);
    expect(container.querySelector('[data-amount="100.0000"]')).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No lines")).toBeInTheDocument();
  });
});
