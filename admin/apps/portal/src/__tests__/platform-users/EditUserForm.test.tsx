import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
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
      <Toaster />
    </QueryClientProvider>,
  );
}

async function selectRole(name: RegExp) {
  await userEvent.click(screen.getByRole("combobox", { name: /role/i }));
  await userEvent.click(screen.getByRole("option", { name }));
}

describe("EditUserForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Sonner's toast store is module-global; clear it between tests.
    toast.dismiss();
  });

  it("submits a name-only change directly without the maker-checker dialog", async () => {
    patchUser.mockResolvedValue({ data: { ...user }, error: undefined });
    renderForm();
    const name = screen.getByLabelText(/full name/i);
    await userEvent.clear(name);
    await userEvent.type(name, "Ada Renamed");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() =>
      expect(patchUser).toHaveBeenCalledWith("u1", {
        full_name: "Ada Renamed",
        is_active: true,
        role: "support",
      }),
    );
    expect(screen.queryByText(/create an approval request, not execute/i)).toBeNull();
    // Direct-save feedback, not the approval-request copy.
    expect(await screen.findByText(/changes saved/i)).toBeInTheDocument();
  });

  it("relabels the submit button to Request Change when a sensitive field is dirty", async () => {
    renderForm();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeInTheDocument();
    await selectRole(/admin/i);
    expect(screen.getByRole("button", { name: /request change/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save$/i })).toBeNull();
  });

  it("requires confirmation via the maker-checker dialog when role changes", async () => {
    patchUser.mockResolvedValue({ data: { ...user }, error: undefined });
    renderForm();
    await selectRole(/admin/i);
    await userEvent.click(screen.getByRole("button", { name: /request change/i }));
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
    // Approval-request feedback so the operator knows nothing executed yet.
    expect(await screen.findByText(/approval request created/i)).toBeInTheDocument();
  });

  it("surfaces a mutation error and keeps the dialog open", async () => {
    patchUser.mockResolvedValue({
      data: undefined,
      error: { detail: "A pending approval already exists for this user" },
    });
    renderForm();
    await selectRole(/admin/i);
    await userEvent.click(screen.getByRole("button", { name: /request change/i }));
    await userEvent.click(
      await screen.findByRole("button", { name: /create approval request/i }),
    );
    expect(
      await screen.findByText(/a pending approval already exists/i),
    ).toBeInTheDocument();
    // Dialog stays open so the operator can see the action did not proceed.
    expect(screen.getByText(/create an approval request, not execute/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("associates help text with the role select and active checkbox", () => {
    renderForm();
    const combo = screen.getByRole("combobox", { name: /role/i });
    const comboDescribedBy = combo.getAttribute("aria-describedby");
    expect(comboDescribedBy).toBeTruthy();
    expect(document.getElementById(comboDescribedBy as string)?.textContent).toMatch(
      /changing the role creates an approval request/i,
    );

    const checkbox = screen.getByRole("checkbox", { name: /active/i });
    const checkboxDescribedBy = checkbox.getAttribute("aria-describedby");
    expect(checkboxDescribedBy).toBeTruthy();
    expect(
      document.getElementById(checkboxDescribedBy as string)?.textContent,
    ).toMatch(/deactivating a user creates an approval request/i);
  });
});
