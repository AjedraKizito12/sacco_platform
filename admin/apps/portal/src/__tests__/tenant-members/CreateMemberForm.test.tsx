// admin/apps/portal/src/__tests__/tenant-members/CreateMemberForm.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const create = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { members: { create } } }),
}));

import { CreateMemberForm } from "../../../app/(tenant-authed)/members/new/_components/CreateMemberForm";

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <CreateMemberForm />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("CreateMemberForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("rejects an empty full name without calling the API", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText(/date of birth/i), "2000-01-01");
    await userEvent.click(screen.getByRole("button", { name: /register member/i }));
    expect(await screen.findByText(/full name is required/i)).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it("creates a member and redirects to its detail on success", async () => {
    create.mockResolvedValue({ data: { id: "m9" }, error: undefined });
    renderForm();
    await userEvent.type(screen.getByLabelText(/full name/i), "Ada Loan");
    await userEvent.type(screen.getByLabelText(/date of birth/i), "2000-01-01");
    await userEvent.click(screen.getByLabelText(/gender/i));
    await userEvent.click(await screen.findByRole("option", { name: "Female" }));
    await userEvent.click(screen.getByRole("button", { name: /register member/i }));

    expect(await screen.findByText(/member registered/i)).toBeInTheDocument();
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({ full_name: "Ada Loan", date_of_birth: "2000-01-01", gender: "F" }),
    );
    expect(push).toHaveBeenCalledWith("/members/m9");
  });
});
