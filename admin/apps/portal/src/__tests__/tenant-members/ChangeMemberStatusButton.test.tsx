// admin/apps/portal/src/__tests__/tenant-members/ChangeMemberStatusButton.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const changeStatus = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { members: { changeStatus } } }),
}));

import { ChangeMemberStatusButton } from "../../../app/(tenant-authed)/members/[id]/_components/ChangeMemberStatusButton";

function renderButton() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ChangeMemberStatusButton memberId="m1" currentStatus="active" />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("ChangeMemberStatusButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("offers only active/suspended/exited and creates an approval request", async () => {
    changeStatus.mockResolvedValue({ data: { approval_request_id: "a1", status: "active" }, error: undefined });
    renderButton();

    await userEvent.click(screen.getByRole("button", { name: /change status/i }));
    await userEvent.click(await screen.findByRole("combobox"));

    // Only the three backend-permitted statuses are offered.
    expect(await screen.findByRole("option", { name: "Suspended" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Active" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Exited" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /prospect|dormant|deceased/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("option", { name: "Suspended" }));
    await userEvent.type(
      screen.getByLabelText(/reason/i),
      "Member missed three consecutive savings deposits",
    );
    await userEvent.click(screen.getByRole("button", { name: /request status change/i }));

    // Maker-checker confirm dialog with the locked copy.
    const confirmButton = await screen.findByRole("button", { name: /create approval request/i });
    expect(screen.getByText(/create an approval request, not execute/i)).toBeInTheDocument();
    await userEvent.click(confirmButton);

    expect(await screen.findByText(/pending approval/i)).toBeInTheDocument();
    expect(changeStatus).toHaveBeenCalledWith(
      "m1",
      expect.objectContaining({
        new_status: "suspended",
        reason: "Member missed three consecutive savings deposits",
      }),
    );
  });
});
