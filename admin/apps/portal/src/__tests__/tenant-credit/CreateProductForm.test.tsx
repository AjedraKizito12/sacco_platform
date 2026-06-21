// admin/apps/portal/src/__tests__/tenant-credit/CreateProductForm.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createProduct = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { credit: { createProduct } } }),
}));

import {
  CreateProductForm,
  type GlAccountOption,
} from "../../../app/(tenant-authed)/credit/products/new/_components/CreateProductForm";

const GL = "1200";
const glAccounts: GlAccountOption[] = [
  { id: "g1", code: GL, name: "Loans Receivable", account_type: "asset" },
];

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <CreateProductForm glAccounts={glAccounts} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

async function pickGl(label: RegExp) {
  await userEvent.click(screen.getByLabelText(label));
  await userEvent.click(await screen.findByRole("option", { name: /Loans Receivable/ }));
}

describe("CreateProductForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("blocks submit on a blank name", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: /create product/i }));
    expect(createProduct).not.toHaveBeenCalled();
  });

  it("creates a product with corrected enums + GL codes and redirects", async () => {
    createProduct.mockResolvedValue({ data: { id: "p9" }, error: undefined });
    renderForm();

    await userEvent.type(screen.getByLabelText(/^name/i), "Personal Loan");
    await userEvent.type(screen.getByLabelText(/interest rate/i), "18.5");
    await userEvent.type(screen.getByLabelText(/max term/i), "24");
    await userEvent.type(screen.getByLabelText(/minimum amount/i), "100000");
    await userEvent.type(screen.getByLabelText(/maximum amount/i), "5000000");
    await userEvent.click(screen.getByText("Member savings"));
    await pickGl(/principal receivable/i);
    await pickGl(/interest receivable/i);
    await pickGl(/interest income/i);
    await pickGl(/loan-loss/i);

    await userEvent.click(screen.getByRole("button", { name: /create product/i }));

    expect(await screen.findByText(/product created/i)).toBeInTheDocument();
    const call = createProduct.mock.calls[0]![0];
    expect(call).toMatchObject({
      name: "Personal Loan",
      interest_method: "reducing_balance",
      repayment_frequency: "monthly",
      repayment_allocation: "INTEREST_PRINCIPAL",
      required_approvals: "1",
      disbursement_destinations: ["member_savings"],
      gl_principal_receivable_code: GL,
      gl_interest_receivable_code: GL,
      gl_interest_income_code: GL,
      gl_loan_loss_expense_code: GL,
    });
    expect(push).toHaveBeenCalledWith("/credit");
  });
});
