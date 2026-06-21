// admin/apps/portal/src/__tests__/tenant-credit/LoanWorkoutActions.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const writeOff = vi.fn();
const restructure = vi.fn();
const recover = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { credit: { writeOff, restructure, recover } } }),
}));

import {
  LoanWorkoutActions,
  type GlAccountOption,
} from "../../../app/(tenant-authed)/credit/loans/[id]/_components/LoanWorkoutActions";

const glAccounts: GlAccountOption[] = [
  { id: "g1", code: "5100", name: "Loan Loss", account_type: "expense" },
];

function renderActions(status: string) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <LoanWorkoutActions loanId="l1" status={status} glAccounts={glAccounts} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("LoanWorkoutActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("writes off directly (direct=true)", async () => {
    writeOff.mockResolvedValue({
      data: { direct: true, approval_request_id: null, journal_entry_id: "j1" },
      error: undefined,
    });
    renderActions("disbursed");
    await userEvent.click(screen.getByRole("button", { name: /write off/i }));
    await userEvent.type(screen.getByLabelText(/amount/i), "500000");
    await userEvent.type(screen.getByLabelText(/reason/i), "Borrower deceased; collateral exhausted.");
    await userEvent.click(screen.getByRole("button", { name: /post write-off/i }));

    expect(await screen.findByText(/loan written off/i)).toBeInTheDocument();
    expect(writeOff).toHaveBeenCalledWith("l1", expect.objectContaining({ amount: "500000" }));
  });

  it("submits a restructure for approval", async () => {
    restructure.mockResolvedValue({ data: { approval_request_id: "ar1" }, error: undefined });
    renderActions("disbursed");
    await userEvent.click(screen.getByRole("button", { name: /restructure/i }));
    await userEvent.type(screen.getByLabelText(/periods/i), "3");
    await userEvent.type(
      screen.getByLabelText(/reason/i),
      "Borrower lost job, extending the term to ease repayment",
    );
    await userEvent.click(screen.getByRole("button", { name: /request restructuring/i }));

    expect(await screen.findByText(/pending approval/i)).toBeInTheDocument();
    expect(restructure).toHaveBeenCalledWith(
      "l1",
      expect.objectContaining({ restructuring_type: "term_extension", periods_added: "3" }),
    );
  });

  it("shows Recover only when written off", async () => {
    recover.mockResolvedValue({ data: { journal_entry_id: "j2" }, error: undefined });
    renderActions("written_off");
    expect(screen.queryByRole("button", { name: /write off/i })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /recover/i }));
    await userEvent.type(screen.getByLabelText(/amount/i), "100000");
    await userEvent.type(screen.getByLabelText(/reason/i), "Partial recovery from guarantor");
    await userEvent.click(screen.getByRole("button", { name: /post recovery/i }));

    expect(await screen.findByText(/recovery posted/i)).toBeInTheDocument();
    expect(recover).toHaveBeenCalledWith("l1", expect.objectContaining({ amount: "100000" }));
  });
});
