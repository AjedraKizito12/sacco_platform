// admin/apps/portal/src/__tests__/tenant-credit/RecordRepaymentButton.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const recordRepayment = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { credit: { recordRepayment } } }),
}));

import {
  RecordRepaymentButton,
  type GlAccountOption,
} from "../../../app/(tenant-authed)/credit/loans/[id]/_components/RecordRepaymentButton";

const GL = "550e8400-e29b-41d4-a716-446655440050";
const glAccounts: GlAccountOption[] = [
  { id: GL, code: "1010", name: "Cash in Hand", account_type: "asset" },
];

function renderButton() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <RecordRepaymentButton loanId="l1" glAccounts={glAccounts} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("RecordRepaymentButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("records a repayment", async () => {
    recordRepayment.mockResolvedValue({ data: { id: "r1" }, error: undefined });
    renderButton();
    await userEvent.click(screen.getByRole("button", { name: /record repayment/i }));
    await userEvent.type(screen.getByLabelText(/amount/i), "95000");
    await userEvent.click(screen.getByLabelText(/payment.*account/i));
    await userEvent.click(await screen.findByRole("option", { name: /Cash in Hand/ }));
    await userEvent.click(screen.getByRole("button", { name: /post repayment/i }));

    expect(await screen.findByText(/repayment recorded/i)).toBeInTheDocument();
    expect(recordRepayment).toHaveBeenCalledWith(
      "l1",
      expect.objectContaining({ amount: "95000", payment_account_id: GL }),
    );
  });
});
