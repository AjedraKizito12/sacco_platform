// admin/apps/portal/src/__tests__/platform-billing/PendingPaymentsTable.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

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

const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/platform/billing/payments",
}));

const rejectPayment = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { billing: { rejectPayment } } }),
}));

import {
  PendingPaymentsTable,
  type PendingPaymentRow,
} from "../../../app/platform/(authed)/billing/payments/_components/PendingPaymentsTable";

const row: PendingPaymentRow = {
  id: "pay1", invoice_id: "i1", invoice_number: "INV-2026-000001",
  amount: "120000", currency: "UGX", payment_method: "bank_transfer",
  recorded_at: "2026-06-10T00:00:00Z", status: "pending",
};

function renderTable(rows: PendingPaymentRow[], canReject = true) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <PendingPaymentsTable rows={rows} canReject={canReject} />
        <Toaster />
      </TenantCurrencyProvider>
    </QueryClientProvider>,
  );
}

describe("PendingPaymentsTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("renders a pending payment with a linked invoice + amount", () => {
    renderTable([row]);
    expect(screen.getByRole("link", { name: /INV-2026-000001/i })).toHaveAttribute(
      "href",
      "/platform/billing/invoices/i1",
    );
    expect(screen.getByText(/120,000/)).toBeInTheDocument();
  });

  it("rejects a payment with a reason via the confirm dialog", async () => {
    rejectPayment.mockResolvedValue({ data: { status: "rejected" }, error: undefined });
    renderTable([row]);
    await userEvent.click(screen.getByRole("button", { name: /reject/i }));
    await userEvent.type(screen.getByLabelText(/reason/i), "Bank reference does not match");
    await userEvent.click(screen.getByRole("button", { name: /^reject payment$/i }));
    await waitFor(() =>
      expect(rejectPayment).toHaveBeenCalledWith("pay1", { reason: "Bank reference does not match" }),
    );
    expect(await screen.findByText(/payment rejected/i)).toBeInTheDocument();
  });

  it("hides Reject without permission", () => {
    renderTable([row], false);
    expect(screen.queryByRole("button", { name: /reject/i })).toBeNull();
  });

  it("renders the empty state with no rows", () => {
    renderTable([]);
    expect(screen.getByText(/no payments awaiting/i)).toBeInTheDocument();
  });
});
