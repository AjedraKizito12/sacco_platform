// admin/apps/portal/src/__tests__/tenant-ledger/CreateAccountForm.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createAccount = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { ledger: { createAccount } } }),
}));

import {
  CreateAccountForm,
  type AccountOption,
} from "../../../app/(tenant-authed)/ledger/accounts/new/_components/CreateAccountForm";

const parents: AccountOption[] = [{ id: "p1", code: "1000", name: "Assets" }];

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <CreateAccountForm parents={parents} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("CreateAccountForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("blocks submit on a blank code", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));
    expect(createAccount).not.toHaveBeenCalled();
  });

  it("creates an account and redirects", async () => {
    createAccount.mockResolvedValue({ data: { id: "a9" }, error: undefined });
    renderForm();
    await userEvent.type(screen.getByLabelText(/^code/i), "1010");
    await userEvent.type(screen.getByLabelText(/^name/i), "Cash");
    await userEvent.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/account created/i)).toBeInTheDocument();
    const call = createAccount.mock.calls[0]![0];
    expect(call).toMatchObject({ code: "1010", name: "Cash", account_type: "asset" });
    expect(call).not.toHaveProperty("parent_id");
    expect(call).not.toHaveProperty("description");
    expect(push).toHaveBeenCalledWith("/ledger/accounts");
  });
});
