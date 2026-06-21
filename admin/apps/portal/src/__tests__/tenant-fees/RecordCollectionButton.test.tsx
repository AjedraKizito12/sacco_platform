// admin/apps/portal/src/__tests__/tenant-fees/RecordCollectionButton.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const recordCollection = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { fees: { recordCollection } } }),
}));

import {
  RecordCollectionButton,
  type GlAccountOption,
} from "../../../app/(tenant-authed)/fees/assessments/[id]/_components/RecordCollectionButton";

const CA = "550e8400-e29b-41d4-a716-446655440010";
const A1 = "550e8400-e29b-41d4-a716-446655440020";
const glAccounts: GlAccountOption[] = [
  { id: CA, code: "1010", name: "Cash", account_type: "asset" },
];

function renderButton(status: string) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <RecordCollectionButton assessmentId={A1} status={status} glAccounts={glAccounts} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("RecordCollectionButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("records a collection", async () => {
    recordCollection.mockResolvedValue({ data: { id: "c1" }, error: undefined });
    renderButton("assessed");
    await userEvent.click(screen.getByRole("button", { name: /record collection/i }));
    await userEvent.type(screen.getByLabelText(/amount/i), "5000");
    await userEvent.click(screen.getByLabelText(/contra/i));
    await userEvent.click(await screen.findByRole("option", { name: /Cash/ }));
    await userEvent.click(screen.getByRole("button", { name: /^record$/i }));

    expect(await screen.findByText(/collection recorded/i)).toBeInTheDocument();
    expect(recordCollection).toHaveBeenCalledWith(
      expect.objectContaining({
        fee_assessment_id: A1,
        amount: "5000",
        method: "cash",
        contra_account_id: CA,
      }),
    );
  });

  it("renders nothing when the assessment is paid", () => {
    renderButton("paid");
    expect(screen.queryByRole("button", { name: /record collection/i })).not.toBeInTheDocument();
  });
});
