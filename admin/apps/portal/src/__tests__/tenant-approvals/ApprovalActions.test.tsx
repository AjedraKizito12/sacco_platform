import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

const approveTenant = vi.fn();
const rejectTenant = vi.fn();
const cancelTenant = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { makerChecker: { approveTenant, rejectTenant, cancelTenant } } }),
}));

import { ApprovalActions } from "../../../app/(tenant-authed)/approvals/[id]/_components/ApprovalActions";

const A = "550e8400-e29b-41d4-a716-446655440000"; // request id
const ME = "550e8400-e29b-41d4-a716-446655440001";
const OTHER = "550e8400-e29b-41d4-a716-446655440002";

function renderActions(props: {
  status: string;
  requestedBy: string;
  currentUserId: string;
}) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ApprovalActions
        requestId={A}
        subjectLabel="Write off loan"
        status={props.status}
        requestedBy={props.requestedBy}
        currentUserId={props.currentUserId}
      />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("ApprovalActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("non-self pending shows Approve + Reject and approves", async () => {
    approveTenant.mockResolvedValue({ data: {}, error: undefined });
    renderActions({ status: "pending", requestedBy: OTHER, currentUserId: ME });

    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await userEvent.click(screen.getByRole("button", { name: "Approve and execute" }));

    await waitFor(() => expect(approveTenant).toHaveBeenCalledWith(A, expect.any(Object)));
  });

  it("self request shows Cancel + notice, hides Approve", () => {
    renderActions({ status: "pending", requestedBy: ME, currentUserId: ME });
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel request" })).toBeInTheDocument();
  });

  it("renders no actions when not pending", () => {
    renderActions({ status: "approved", requestedBy: OTHER, currentUserId: ME });
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel request" })).not.toBeInTheDocument();
  });
});
