// admin/apps/portal/src/__tests__/tenant-fees/CreateFeeTypeForm.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createType = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { fees: { createType } } }),
}));

import {
  CreateFeeTypeForm,
  type GlAccountOption,
} from "../../../app/(tenant-authed)/fees/types/new/_components/CreateFeeTypeForm";

const GL = "4200";
const glAccounts: GlAccountOption[] = [
  { id: "g1", code: GL, name: "Fee Income", account_type: "income" },
];

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <CreateFeeTypeForm glAccounts={glAccounts} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

async function pickGl(label: RegExp) {
  await userEvent.click(screen.getByLabelText(label));
  await userEvent.click(await screen.findByRole("option", { name: /Fee Income/ }));
}

describe("CreateFeeTypeForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("blocks submit on a blank code", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: /create fee type/i }));
    expect(createType).not.toHaveBeenCalled();
  });

  it("creates a fee type and redirects", async () => {
    createType.mockResolvedValue({ data: { id: "f9" }, error: undefined });
    renderForm();
    await userEvent.type(screen.getByLabelText(/^code/i), "annual");
    await userEvent.type(screen.getByLabelText(/^name/i), "Annual Fee");
    await userEvent.type(screen.getByLabelText(/amount/i), "20000");
    await pickGl(/income gl/i);
    await pickGl(/receivable gl/i);
    await userEvent.click(screen.getByRole("button", { name: /create fee type/i }));

    expect(await screen.findByText(/fee type created/i)).toBeInTheDocument();
    const call = createType.mock.calls[0]![0];
    expect(call).toMatchObject({
      code: "annual",
      name: "Annual Fee",
      applicable_to: "member",
      amount_kind: "fixed",
      trigger_kind: "manual",
      gl_income_account_code: GL,
      gl_receivable_account_code: GL,
    });
    expect(push).toHaveBeenCalledWith("/fees/types");
  });
});
