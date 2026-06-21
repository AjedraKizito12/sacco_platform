// admin/apps/portal/src/__tests__/tenant-fees/EditFeeTypeForm.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";
import type { FeeTypeOut } from "@sacco/schemas";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const patchType = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { fees: { patchType } } }),
}));

import { EditFeeTypeForm } from "../../../app/(tenant-authed)/fees/types/[id]/_components/EditFeeTypeForm";

const feeType: FeeTypeOut = {
  id: "f1", code: "annual", name: "Annual Fee", description: "Yearly", applicable_to: "member",
  amount_kind: "fixed", amount: "20000.00", percentage_basis: null, percentage_rate: null,
  currency: "UGX", trigger_kind: "schedule", event_name: null, schedule_config: null,
  gl_income_account_code: "4200", gl_receivable_account_code: "1300", is_active: true,
  requires_collection: false,
};

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <EditFeeTypeForm feeType={feeType} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("EditFeeTypeForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("prefills the name", () => {
    renderForm();
    expect(screen.getByLabelText(/name/i)).toHaveValue("Annual Fee");
  });

  it("patches the changed name and refreshes", async () => {
    patchType.mockResolvedValue({ data: { id: "f1" }, error: undefined });
    renderForm();
    const name = screen.getByLabelText(/name/i);
    await userEvent.clear(name);
    await userEvent.type(name, "Membership Fee");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await screen.findByText(/fee type updated/i)).toBeInTheDocument();
    expect(patchType).toHaveBeenCalledWith(
      "f1",
      expect.objectContaining({ name: "Membership Fee" }),
    );
    expect(refresh).toHaveBeenCalled();
  });
});
