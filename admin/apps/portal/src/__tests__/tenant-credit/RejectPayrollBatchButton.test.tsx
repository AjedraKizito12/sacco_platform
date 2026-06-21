// admin/apps/portal/src/__tests__/tenant-credit/RejectPayrollBatchButton.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const rejectPayrollBatch = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { credit: { rejectPayrollBatch } } }),
}));

import { RejectPayrollBatchButton } from "../../../app/(tenant-authed)/credit/payroll/[id]/_components/RejectPayrollBatchButton";

function renderButton(status: string) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <RejectPayrollBatchButton batchId="b1" status={status} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("RejectPayrollBatchButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("rejects a pending_review batch via confirm", async () => {
    rejectPayrollBatch.mockResolvedValue({ data: { id: "b1" }, error: undefined });
    renderButton("pending_review");
    await userEvent.click(screen.getByRole("button", { name: "Reject batch" }));
    const confirm = await screen.findByRole("button", { name: "Reject" });
    await userEvent.click(confirm);
    expect(await screen.findByText(/batch rejected/i)).toBeInTheDocument();
    expect(rejectPayrollBatch).toHaveBeenCalledWith("b1", {});
  });

  it("renders nothing when not pending_review", () => {
    renderButton("applied");
    expect(screen.queryByRole("button", { name: "Reject batch" })).not.toBeInTheDocument();
  });
});
