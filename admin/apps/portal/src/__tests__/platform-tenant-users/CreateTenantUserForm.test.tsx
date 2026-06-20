import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createUser = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { createUser } } }),
}));

import { CreateTenantUserForm } from "../../../app/platform/(authed)/tenants/[id]/users/new/_components/CreateTenantUserForm";

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <CreateTenantUserForm tenantId="t1" />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("CreateTenantUserForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("rejects an invalid email without calling the API", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText(/email/i), "nope");
    await userEvent.type(screen.getByLabelText(/full name/i), "Ada");
    await userEvent.click(screen.getByRole("button", { name: /create user/i }));
    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
    expect(createUser).not.toHaveBeenCalled();
  });

  it("shows the one-time reset token in a modal on success", async () => {
    createUser.mockResolvedValue({
      data: { password_reset_token: "TKN-123", password_reset_expires_in: 86400 },
      error: undefined,
    });
    renderForm();
    await userEvent.type(screen.getByLabelText(/email/i), "ada@sacco.test");
    await userEvent.type(screen.getByLabelText(/full name/i), "Ada Loan");
    await userEvent.click(screen.getByRole("button", { name: /create user/i }));
    expect(await screen.findByText("TKN-123")).toBeInTheDocument();
    expect(createUser).toHaveBeenCalledWith(
      "t1",
      expect.objectContaining({ email: "ada@sacco.test", full_name: "Ada Loan" }),
    );
  });
});
