import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createUser = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { admin: { createUser } } }),
}));

import { CreateUserForm } from "../../../app/platform/(authed)/users/new/_components/CreateUserForm";

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <CreateUserForm />
    </QueryClientProvider>,
  );
}

describe("CreateUserForm", () => {
  it("shows a validation error for an invalid email", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText(/email/i), "nope");
    await userEvent.type(screen.getByLabelText(/full name/i), "Ada");
    await userEvent.click(screen.getByRole("button", { name: /create user/i }));
    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
    expect(createUser).not.toHaveBeenCalled();
  });

  it("submits a valid payload and redirects", async () => {
    createUser.mockResolvedValue({ data: { id: "new-id" }, error: undefined });
    renderForm();
    await userEvent.type(screen.getByLabelText(/email/i), "ada@example.com");
    await userEvent.type(screen.getByLabelText(/full name/i), "Ada Ops");
    await userEvent.click(screen.getByRole("button", { name: /create user/i }));
    await waitFor(() =>
      expect(createUser).toHaveBeenCalledWith({
        email: "ada@example.com",
        full_name: "Ada Ops",
        role: "support",
      }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/platform/users"));
  });
});
