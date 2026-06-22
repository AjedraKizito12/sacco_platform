// admin/apps/portal/src/__tests__/tenant-ledger/JournalEntriesTable.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { JournalEntryOut } from "@sacco/schemas";

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
  usePathname: () => "/ledger/journal-entries",
}));

import { JournalEntriesTable } from "../../../app/(tenant-authed)/ledger/journal-entries/_components/JournalEntriesTable";

const entry: JournalEntryOut = {
  id: "e1",
  reference: "JV-1",
  description: "Opening balance",
  posted_by: "u1",
  posted_at: "2026-06-22T10:00:00Z",
  idempotency_key: "k1",
  lines: [
    { id: "l1", account_id: "a1", debit_amount: "100", credit_amount: "0", description: null },
  ],
};

function renderTable(rows: JournalEntryOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <JournalEntriesTable rows={rows} />
    </TenantCurrencyProvider>,
  );
}

describe("JournalEntriesTable", () => {
  it("links the reference to detail and shows the line count", () => {
    const { container } = renderTable([entry]);
    expect(screen.getByRole("link", { name: "JV-1" })).toHaveAttribute(
      "href",
      "/ledger/journal-entries/e1",
    );
    expect(container.querySelector('[data-value="1"]')).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    renderTable([]);
    expect(screen.getByText("No journal entries yet")).toBeInTheDocument();
  });
});
