// admin/apps/portal/src/__tests__/tenant-fees/CreateAssessmentForm.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createAssessment = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { fees: { createAssessment } } }),
}));

import {
  CreateAssessmentForm,
  type FeeTypeOption,
  type TargetMap,
} from "../../../app/(tenant-authed)/fees/assessments/new/_components/CreateAssessmentForm";

const FT = "550e8400-e29b-41d4-a716-446655440000";
const M1 = "550e8400-e29b-41d4-a716-446655440001";
const L1 = "550e8400-e29b-41d4-a716-446655440002";
const feeTypes: FeeTypeOption[] = [{ id: FT, code: "annual", name: "Annual Fee" }];
const targets: TargetMap = {
  member: [{ id: M1, label: "Ada Loan (M-0001)" }],
  loan: [{ id: L1, label: "LN-1 · Ada Loan" }],
  savings_account: [],
  share_account: [],
};

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <CreateAssessmentForm feeTypes={feeTypes} targets={targets} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("CreateAssessmentForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("switches target options when target_type changes", async () => {
    renderForm();
    // default target_type = member
    await userEvent.click(screen.getByLabelText(/target record/i));
    expect(await screen.findByRole("option", { name: "Ada Loan (M-0001)" })).toBeInTheDocument();
    // close the listbox, switch type to loan
    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByLabelText(/target type/i));
    await userEvent.click(await screen.findByRole("option", { name: "Loan" }));
    await userEvent.click(screen.getByLabelText(/target record/i));
    expect(await screen.findByRole("option", { name: "LN-1 · Ada Loan" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Ada Loan (M-0001)" })).not.toBeInTheDocument();
  });

  it("creates a member assessment and redirects", async () => {
    createAssessment.mockResolvedValue({ data: { id: "a9" }, error: undefined });
    renderForm();
    await userEvent.click(screen.getByLabelText(/fee type/i));
    await userEvent.click(await screen.findByRole("option", { name: /Annual Fee/ }));
    await userEvent.click(screen.getByLabelText(/target record/i));
    await userEvent.click(await screen.findByRole("option", { name: "Ada Loan (M-0001)" }));
    await userEvent.type(screen.getByLabelText(/period start/i), "2026-06-01");
    await userEvent.click(screen.getByRole("button", { name: /create assessment/i }));

    expect(await screen.findByText(/assessment created/i)).toBeInTheDocument();
    expect(createAssessment).toHaveBeenCalledWith(
      expect.objectContaining({
        fee_type_id: FT,
        target_type: "member",
        target_id: M1,
        period_start: "2026-06-01",
      }),
    );
    expect(push).toHaveBeenCalledWith("/fees/assessments/a9");
  });
});
