import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { TenantUserOut } from "@sacco/schemas";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const patchUser = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { patchUser } } }),
}));

import { EditTenantUserForm } from "../../../app/platform/(authed)/tenants/[id]/users/[userId]/edit/_components/EditTenantUserForm";

const user: TenantUserOut = {
  id: "u1",
  email: "ada@sacco.test",
  full_name: "Ada Loan",
  is_active: true,
  is_admin: false,
  last_login_at: null,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
  impersonation_id: null,
};

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <EditTenantUserForm tenantId="t1" user={user} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("EditTenantUserForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("pre-fills the name and submits a direct PATCH (no maker-checker)", async () => {
    patchUser.mockResolvedValue({ data: {}, error: undefined });
    renderForm();
    expect(screen.getByDisplayValue("Ada Loan")).toBeInTheDocument();
    // No maker-checker confirm copy on a direct tenant-user edit.
    expect(screen.queryByText(/approval request/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => expect(patchUser).toHaveBeenCalledWith("t1", "u1", expect.any(Object)));
  });
});
