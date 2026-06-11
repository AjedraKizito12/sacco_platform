import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PlatformUserOut } from "@sacco/schemas";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const patchUser = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { admin: { patchUser } } }),
}));

import { EditUserForm } from "../../../app/platform/(authed)/users/[id]/edit/_components/EditUserForm";

const user: PlatformUserOut = {
  id: "u1", email: "ada@example.com", full_name: "Ada Ops", is_active: true,
  is_superuser: false, role: "support", created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z", last_login_at: null,
};

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <EditUserForm user={user} />
    </QueryClientProvider>,
  );
}

describe("EditUserForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("submits a name-only change directly without the maker-checker dialog", async () => {
    patchUser.mockResolvedValue({ data: { ...user }, error: undefined });
    renderForm();
    const name = screen.getByLabelText(/full name/i);
    await userEvent.clear(name);
    await userEvent.type(name, "Ada Renamed");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(patchUser).toHaveBeenCalledWith("u1", {
        full_name: "Ada Renamed",
        is_active: true,
        role: "support",
      }),
    );
    expect(screen.queryByText(/create an approval request, not execute/i)).toBeNull();
  });

  it("requires confirmation via the maker-checker dialog when role changes", async () => {
    patchUser.mockResolvedValue({ data: { ...user }, error: undefined });
    renderForm();
    await userEvent.click(screen.getByRole("combobox", { name: /role/i }));
    await userEvent.click(screen.getByRole("option", { name: /admin/i }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText(/create an approval request, not execute/i)).toBeInTheDocument();
    expect(patchUser).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /create approval request/i }));
    await waitFor(() =>
      expect(patchUser).toHaveBeenCalledWith("u1", {
        full_name: "Ada Ops",
        is_active: true,
        role: "admin",
      }),
    );
  });
});
