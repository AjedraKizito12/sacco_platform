// admin/apps/portal/src/__tests__/tenant-credit/ApplicationActions.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const approveApplication = vi.fn();
const rejectApplication = vi.fn();
const withdrawApplication = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({
    resources: {
      credit: { approveApplication, rejectApplication, withdrawApplication },
    },
  }),
}));

import { ApplicationActions } from "../../../app/(tenant-authed)/credit/applications/[id]/_components/ApplicationActions";

function renderActions() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ApplicationActions applicationId="a1" />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("ApplicationActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("approves via a confirm dialog", async () => {
    approveApplication.mockResolvedValue({ data: { id: "a1" }, error: undefined });
    renderActions();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    // ConfirmDialog confirm button also labelled "Approve" — pick the one in the dialog
    const confirmButtons = await screen.findAllByRole("button", { name: "Approve" });
    await userEvent.click(confirmButtons[confirmButtons.length - 1]!);
    expect(await screen.findByText(/application approved/i)).toBeInTheDocument();
    expect(approveApplication).toHaveBeenCalledWith("a1", {});
  });

  it("requires a reason to reject", async () => {
    rejectApplication.mockResolvedValue({ data: { id: "a1" }, error: undefined });
    renderActions();
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    await userEvent.click(screen.getByRole("button", { name: /reject application/i }));
    expect(rejectApplication).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText(/reason/i), "Insufficient collateral");
    await userEvent.click(screen.getByRole("button", { name: /reject application/i }));
    expect(await screen.findByText(/application rejected/i)).toBeInTheDocument();
    expect(rejectApplication).toHaveBeenCalledWith("a1", {
      reason: "Insufficient collateral",
    });
  });

  it("withdraws via a confirm dialog", async () => {
    withdrawApplication.mockResolvedValue({ data: { id: "a1" }, error: undefined });
    renderActions();
    await userEvent.click(screen.getByRole("button", { name: "Withdraw" }));
    const confirmButtons = await screen.findAllByRole("button", { name: "Withdraw" });
    await userEvent.click(confirmButtons[confirmButtons.length - 1]!);
    expect(await screen.findByText(/application withdrawn/i)).toBeInTheDocument();
    expect(withdrawApplication).toHaveBeenCalledWith("a1", {});
  });
});
