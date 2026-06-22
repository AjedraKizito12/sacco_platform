// admin/apps/portal/src/__tests__/tenant-ledger/ManualGLForm.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const submitJournalEntry = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { ledger: { submitJournalEntry } } }),
}));

import {
  ManualGLForm,
  type AccountOption,
} from "../../../app/(tenant-authed)/ledger/journal-entries/new/_components/ManualGLForm";

const A = "11111111-1111-1111-1111-111111111111";
const B = "22222222-2222-2222-2222-222222222222";
const accounts: AccountOption[] = [
  { id: A, code: "1010", name: "Cash" },
  { id: B, code: "4000", name: "Income" },
];

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <ManualGLForm accounts={accounts} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

async function pickAccount(label: RegExp, optionName: RegExp) {
  await userEvent.click(screen.getByLabelText(label));
  await userEvent.click(await screen.findByRole("option", { name: optionName }));
}

describe("ManualGLForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("submits a balanced entry and redirects", async () => {
    submitJournalEntry.mockResolvedValue({
      data: { approval_request_id: "r1", status: "pending" },
      error: undefined,
    });
    renderForm();
    await userEvent.type(screen.getByLabelText(/^reference/i), "JV-1");
    await userEvent.type(screen.getByLabelText(/^description/i), "Opening");
    await pickAccount(/account 1/i, /1010 — Cash/);
    await pickAccount(/account 2/i, /4000 — Income/);
    await userEvent.type(screen.getByLabelText(/debit 1/i), "100");
    await userEvent.type(screen.getByLabelText(/credit 2/i), "100");
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));

    expect(await screen.findByText(/pending approval/i)).toBeInTheDocument();
    expect(submitJournalEntry).toHaveBeenCalledWith(
      expect.objectContaining({
        reference: "JV-1",
        lines: [
          expect.objectContaining({ account_id: A, debit_amount: "100", credit_amount: "0" }),
          expect.objectContaining({ account_id: B, debit_amount: "0", credit_amount: "100" }),
        ],
      }),
    );
    expect(push).toHaveBeenCalledWith("/ledger/journal-entries");
  });

  it("blocks an unbalanced entry", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText(/^reference/i), "JV-2");
    await userEvent.type(screen.getByLabelText(/^description/i), "Bad");
    await pickAccount(/account 1/i, /1010 — Cash/);
    await pickAccount(/account 2/i, /4000 — Income/);
    await userEvent.type(screen.getByLabelText(/debit 1/i), "100");
    await userEvent.type(screen.getByLabelText(/credit 2/i), "50");
    await userEvent.click(screen.getByRole("button", { name: /submit/i }));

    expect(submitJournalEntry).not.toHaveBeenCalled();
  });
});
