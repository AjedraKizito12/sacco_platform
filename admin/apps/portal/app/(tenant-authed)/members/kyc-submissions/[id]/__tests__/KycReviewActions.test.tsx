import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";

const approveKycSubmission = vi.fn().mockResolvedValue({ data: { status: "approved" } });
const rejectKycSubmission = vi.fn().mockResolvedValue({ data: { status: "rejected" } });

vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({
    resources: { members: { approveKycSubmission, rejectKycSubmission } },
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

import { KycReviewActions } from "../_components/KycReviewActions";

function renderActions(submissionId: string, status: string) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <KycReviewActions submissionId={submissionId} status={status} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("KycReviewActions", () => {
  beforeEach(() => {
    approveKycSubmission.mockClear();
    rejectKycSubmission.mockClear();
    toast.dismiss();
  });

  it("renders nothing when the submission is not pending", () => {
    renderActions("s1", "approved");
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
  });

  it("approves after confirmation", async () => {
    const user = userEvent.setup();
    renderActions("s1", "pending");
    await user.click(screen.getByRole("button", { name: /^approve$/i }));
    await user.click(screen.getByRole("button", { name: /approve submission/i }));
    await waitFor(() => expect(approveKycSubmission).toHaveBeenCalledWith("s1"));
  });

  it("requires a reason to reject", async () => {
    const user = userEvent.setup();
    renderActions("s1", "pending");
    await user.click(screen.getByRole("button", { name: /^reject$/i }));
    await user.click(screen.getByRole("button", { name: /reject submission/i }));
    expect(rejectKycSubmission).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText(/reason/i), "ID number looks wrong");
    await user.click(screen.getByRole("button", { name: /reject submission/i }));
    await waitFor(() =>
      expect(rejectKycSubmission).toHaveBeenCalledWith("s1", {
        reason: "ID number looks wrong",
      }),
    );
  });
});
