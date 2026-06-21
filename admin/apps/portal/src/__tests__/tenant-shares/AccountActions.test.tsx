// admin/apps/portal/src/__tests__/tenant-shares/AccountActions.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const purchase = vi.fn();
const redeem = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { shares: { purchase, redeem } } }),
}));

import {
  AccountActions,
  type GlAccountOption,
} from "../../../app/(tenant-authed)/shares/accounts/[id]/_components/AccountActions";

const GL_ID = "550e8400-e29b-41d4-a716-446655440099";
const glAccounts: GlAccountOption[] = [
  { id: GL_ID, code: "1020", name: "Cash in Hand", account_type: "asset" },
];

function renderActions() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <AccountActions accountId="a1" glAccounts={glAccounts} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("AccountActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("posts a purchase directly (no maker-checker)", async () => {
    purchase.mockResolvedValue({ data: { id: "t1" }, error: undefined });
    renderActions();
    await userEvent.click(screen.getByRole("button", { name: "Purchase" }));
    await userEvent.type(screen.getByLabelText(/quantity/i), "5");
    await userEvent.click(screen.getByLabelText(/cash \/ payment gl account/i));
    await userEvent.click(await screen.findByRole("option", { name: /Cash in Hand/ }));
    await userEvent.click(screen.getByRole("button", { name: /post purchase/i }));

    expect(await screen.findByText(/shares purchased/i)).toBeInTheDocument();
    expect(purchase).toHaveBeenCalledWith(
      "a1",
      expect.objectContaining({ quantity: "5", payment_account_id: GL_ID }),
    );
  });

  it("requires maker-checker confirmation for a redemption", async () => {
    redeem.mockResolvedValue({ data: { approval_request_id: "ar1", status: "pending" }, error: undefined });
    renderActions();
    await userEvent.click(screen.getByRole("button", { name: "Redeem" }));
    await userEvent.type(screen.getByLabelText(/quantity/i), "3");
    await userEvent.click(screen.getByLabelText(/cash \/ payment gl account/i));
    await userEvent.click(await screen.findByRole("option", { name: /Cash in Hand/ }));
    await userEvent.click(screen.getByRole("button", { name: /request redemption/i }));

    const confirmButton = await screen.findByRole("button", { name: /create approval request/i });
    expect(screen.getByText(/create an approval request, not execute/i)).toBeInTheDocument();
    expect(redeem).not.toHaveBeenCalled();
    await userEvent.click(confirmButton);

    expect(await screen.findByText(/pending approval/i)).toBeInTheDocument();
    expect(redeem).toHaveBeenCalledWith(
      "a1",
      expect.objectContaining({ quantity: "3", payment_account_id: GL_ID }),
    );
  });
});
