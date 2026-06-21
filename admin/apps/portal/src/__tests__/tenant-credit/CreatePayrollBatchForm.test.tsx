// admin/apps/portal/src/__tests__/tenant-credit/CreatePayrollBatchForm.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createPayrollBatch = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { credit: { createPayrollBatch } } }),
}));

import {
  CreatePayrollBatchForm,
  type GlAccountOption,
  type MemberOption,
} from "../../../app/(tenant-authed)/credit/payroll/new/_components/CreatePayrollBatchForm";

const M1 = "550e8400-e29b-41d4-a716-446655440001";
const CL = "550e8400-e29b-41d4-a716-446655440099";
const members: MemberOption[] = [
  { id: M1, full_name: "Ada Loan", member_number: "M-0001" },
];
const glAccounts: GlAccountOption[] = [
  { id: CL, code: "1099", name: "Payroll Clearing", account_type: "liability" },
];

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <CreatePayrollBatchForm members={members} glAccounts={glAccounts} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("CreatePayrollBatchForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("blocks submit when the row member is empty", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: /create batch/i }));
    expect(createPayrollBatch).not.toHaveBeenCalled();
  });

  it("creates a batch and redirects to its detail", async () => {
    createPayrollBatch.mockResolvedValue({ data: { id: "b9" }, error: undefined });
    renderForm();
    await userEvent.click(screen.getByLabelText(/member/i));
    await userEvent.click(await screen.findByRole("option", { name: /Ada Loan/ }));
    await userEvent.type(screen.getByLabelText(/amount/i), "50000");
    await userEvent.click(screen.getByLabelText(/clearing account/i));
    await userEvent.click(await screen.findByRole("option", { name: /Payroll Clearing/ }));
    await userEvent.click(screen.getByRole("button", { name: /create batch/i }));

    expect(await screen.findByText(/batch created/i)).toBeInTheDocument();
    expect(createPayrollBatch).toHaveBeenCalledWith(
      expect.objectContaining({
        clearing_account_id: CL,
        rows: [{ member_id: M1, amount: "50000" }],
      }),
    );
    expect(push).toHaveBeenCalledWith("/credit/payroll/b9");
  });
});
