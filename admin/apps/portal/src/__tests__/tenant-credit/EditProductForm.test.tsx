// admin/apps/portal/src/__tests__/tenant-credit/EditProductForm.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";
import type { LoanProductOut } from "@sacco/schemas";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const patchProduct = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { credit: { patchProduct } } }),
}));

import { EditProductForm } from "../../../app/(tenant-authed)/credit/products/[id]/_components/EditProductForm";

const product: LoanProductOut = {
  id: "p1",
  name: "Personal Loan",
  description: "Original",
  interest_method: "reducing_balance",
  annual_interest_rate: "18.50",
  repayment_frequency: "monthly",
  max_term_periods: 24,
  min_amount: "100000.00",
  max_amount: "5000000.00",
  required_approvals: 1,
  disbursement_destinations: ["member_savings"],
  repayment_allocation: "INTEREST_PRINCIPAL",
  gl_principal_receivable_code: "1200",
  gl_interest_receivable_code: "1210",
  gl_interest_income_code: "4100",
  gl_loan_loss_expense_code: "5100",
  penalty_fee_type_code: null,
  write_off_threshold: "0.00",
  is_active: true,
  created_at: "2026-06-21T00:00:00Z",
  updated_at: "2026-06-21T00:00:00Z",
};

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <EditProductForm product={product} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("EditProductForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("prefills the current name", () => {
    renderForm();
    expect(screen.getByLabelText(/^name/i)).toHaveValue("Personal Loan");
  });

  it("patches the changed name and refreshes", async () => {
    patchProduct.mockResolvedValue({ data: { id: "p1" }, error: undefined });
    renderForm();
    const name = screen.getByLabelText(/^name/i);
    await userEvent.clear(name);
    await userEvent.type(name, "Renamed Loan");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await screen.findByText(/product updated/i)).toBeInTheDocument();
    expect(patchProduct).toHaveBeenCalledWith(
      "p1",
      expect.objectContaining({ name: "Renamed Loan" }),
    );
    expect(refresh).toHaveBeenCalled();
  });
});
