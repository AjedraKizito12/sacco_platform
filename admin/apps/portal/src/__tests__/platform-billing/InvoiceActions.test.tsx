// admin/apps/portal/src/__tests__/platform-billing/InvoiceActions.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";
import type { InvoiceDetailOut } from "@sacco/schemas";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const recordPayment = vi.fn();
const voidInvoice = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { billing: { recordPayment, voidInvoice } } }),
}));

import { InvoiceActions } from "../../../app/platform/(authed)/billing/invoices/[id]/_components/InvoiceActions";

function invoice(over: Partial<InvoiceDetailOut>): InvoiceDetailOut {
  return {
    id: "i1", invoice_number: "INV-2026-000001", subscription_id: "s1", tenant_id: "t1",
    billing_period_start: "2026-06-01", billing_period_end: "2026-06-30",
    amount_subtotal: "120000", amount_tax: "0", amount_total: "120000", amount_paid: "0",
    currency: "UGX", status: "issued", issued_at: "2026-06-01T00:00:00Z", due_at: "2026-07-01",
    paid_at: null, voided_at: null, void_reason: null, pdf_storage_key: null,
    created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z", line_items: [],
    ...over,
  };
}

function renderActions(inv: InvoiceDetailOut, caps?: { canRecord?: boolean; canVoid?: boolean }) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <InvoiceActions invoice={inv} canRecord={caps?.canRecord ?? true} canVoid={caps?.canVoid ?? true} />
        <Toaster />
      </TenantCurrencyProvider>
    </QueryClientProvider>,
  );
}

describe("InvoiceActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("records a payment via the maker-checker dialog", async () => {
    recordPayment.mockResolvedValue({ data: { status: "pending_approval", payment_id: "pay1" }, error: undefined });
    renderActions(invoice({ status: "issued" }));
    await userEvent.click(screen.getByRole("button", { name: /record payment/i }));
    await userEvent.type(screen.getByLabelText(/amount/i), "120000");
    await userEvent.click(screen.getByRole("combobox", { name: /method/i }));
    await userEvent.click(await screen.findByRole("option", { name: /bank transfer/i }));
    await userEvent.click(screen.getByRole("button", { name: /^record$/i }));
    expect(await screen.findByText(/create an approval request, not execute/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /create approval request/i }));
    await waitFor(() => expect(recordPayment).toHaveBeenCalledTimes(1));
    const [invId, body] = recordPayment.mock.calls[0] as [string, Record<string, unknown>];
    expect(invId).toBe("i1");
    expect(body).toMatchObject({ amount: "120000", payment_method: "bank_transfer" });
    expect(typeof body["idempotency_key"]).toBe("string");
    expect((body["idempotency_key"] as string).length).toBeGreaterThanOrEqual(8);
    expect(await screen.findByText(/payment recorded/i)).toBeInTheDocument();
  });

  it("requests a void via the maker-checker dialog", async () => {
    voidInvoice.mockResolvedValue({ data: { status: "pending_approval" }, error: undefined });
    renderActions(invoice({ status: "issued", amount_paid: "0" }));
    await userEvent.click(screen.getByRole("button", { name: /void/i }));
    await userEvent.type(screen.getByLabelText(/reason/i), "Issued against the wrong tenant");
    await userEvent.click(screen.getByRole("button", { name: /^request void$/i }));
    await userEvent.click(await screen.findByRole("button", { name: /create approval request/i }));
    await waitFor(() => expect(voidInvoice).toHaveBeenCalledWith("i1", { reason: "Issued against the wrong tenant" }));
    expect(await screen.findByText(/void requested/i)).toBeInTheDocument();
  });

  it("hides Void when the invoice has payments or lacks permission", () => {
    const { rerender } = renderActions(invoice({ status: "partial", amount_paid: "5000" }));
    expect(screen.queryByRole("button", { name: /void/i })).toBeNull();
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
          <InvoiceActions invoice={invoice({ status: "issued", amount_paid: "0" })} canRecord canVoid={false} />
        </TenantCurrencyProvider>
      </QueryClientProvider>,
    );
    expect(screen.queryByRole("button", { name: /void/i })).toBeNull();
  });

  it("links Download PDF to the proxy route", () => {
    renderActions(invoice({}));
    expect(screen.getByRole("link", { name: /download pdf/i })).toHaveAttribute(
      "href",
      "/api/billing/invoices/i1/pdf",
    );
  });
});
