import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mutate = vi.fn();
vi.mock("@sacco/api-client", async (importActual) => {
  const actual = await importActual<typeof import("@sacco/api-client")>();
  return {
    ...actual,
    useTypedMutation: () => ({ mutate, isPending: false }),
  };
});
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { makerChecker: {} } }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

import { ApprovalActions } from "../../../app/platform/(authed)/approvals/[id]/_components/ApprovalActions";

const base = {
  requestId: "r1",
  status: "pending",
  requestedBy: "maker",
  subjectLabel: "Void invoice",
};

describe("ApprovalActions", () => {
  it("shows approve + reject for a different user with approve permission", () => {
    render(<ApprovalActions {...base} currentUserId="checker" canApprove />);
    expect(screen.getByRole("button", { name: /^approve$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^reject$/i })).toBeInTheDocument();
    expect(
      screen.queryByText(/cannot approve your own request/i),
    ).not.toBeInTheDocument();
  });

  it("hides approve/reject and shows the self-approval notice + cancel for the requester", () => {
    render(<ApprovalActions {...base} currentUserId="maker" canApprove />);
    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/cannot approve your own request/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel request/i })).toBeInTheDocument();
  });

  it("hides approve/reject for a different user WITHOUT approve permission", () => {
    render(<ApprovalActions {...base} currentUserId="checker" canApprove={false} />);
    expect(screen.queryByRole("button", { name: /^approve$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^reject$/i })).not.toBeInTheDocument();
  });

  it("renders no action buttons when the request is not pending", () => {
    render(<ApprovalActions {...base} status="executed" currentUserId="checker" canApprove />);
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
  });
});
