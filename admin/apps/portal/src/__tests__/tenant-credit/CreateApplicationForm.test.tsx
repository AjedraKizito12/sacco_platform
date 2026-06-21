// admin/apps/portal/src/__tests__/tenant-credit/CreateApplicationForm.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createApplication = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { credit: { createApplication } } }),
}));

import {
  CreateApplicationForm,
  type GlAccountOption,
  type MemberOption,
  type ProductOption,
} from "../../../app/(tenant-authed)/credit/applications/new/_components/CreateApplicationForm";

const MEMBER = "550e8400-e29b-41d4-a716-446655440001";
const PRODUCT = "550e8400-e29b-41d4-a716-446655440003";
const GL = "550e8400-e29b-41d4-a716-446655440050";
const members: MemberOption[] = [
  { id: MEMBER, full_name: "Ada Loan", member_number: "M-0001" },
];
const products: ProductOption[] = [{ id: PRODUCT, name: "Personal Loan" }];
const glAccounts: GlAccountOption[] = [
  { id: GL, code: "1010", name: "Cash in Hand", account_type: "asset" },
];

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <CreateApplicationForm members={members} products={products} glAccounts={glAccounts} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("CreateApplicationForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("blocks submit when required fields are empty", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: /submit application/i }));
    expect(createApplication).not.toHaveBeenCalled();
  });

  it("submits an application and redirects to its detail", async () => {
    createApplication.mockResolvedValue({ data: { id: "a9" }, error: undefined });
    renderForm();
    await userEvent.click(screen.getByLabelText(/product/i));
    await userEvent.click(await screen.findByRole("option", { name: "Personal Loan" }));
    await userEvent.click(screen.getByLabelText(/member/i));
    await userEvent.click(await screen.findByRole("option", { name: /Ada Loan/ }));
    await userEvent.type(screen.getByLabelText(/requested amount/i), "1000000");
    await userEvent.type(screen.getByLabelText(/term/i), "12");
    await userEvent.type(screen.getByLabelText(/purpose/i), "Working capital for the shop");
    await userEvent.click(screen.getByLabelText(/disbursement account/i));
    await userEvent.click(await screen.findByRole("option", { name: /Cash in Hand/ }));
    await userEvent.click(screen.getByRole("button", { name: /submit application/i }));

    expect(await screen.findByText(/application submitted/i)).toBeInTheDocument();
    expect(createApplication).toHaveBeenCalledWith(
      expect.objectContaining({
        loan_product_id: PRODUCT,
        member_id: MEMBER,
        requested_amount: "1000000",
        requested_term_periods: "12",
        disbursement_destination: "cash",
        disbursement_account_id: GL,
      }),
    );
    expect(push).toHaveBeenCalledWith("/credit/applications/a9");
  });
});
