import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { MemberKycRequirementsOut } from "@sacco/schemas";

const putKycRequirements = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { members: { putKycRequirements } } }),
}));

import { MemberKycRequirementsForm } from "../_components/MemberKycRequirementsForm";

const initial: MemberKycRequirementsOut = {
  items: [
    { key: "full_name", label: "Full name", locked: true, required: true },
    { key: "phone", label: "Phone", locked: false, required: true },
    { key: "occupation", label: "Occupation", locked: false, required: false },
  ],
};

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemberKycRequirementsForm initial={initial} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("MemberKycRequirementsForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("renders locked minimums checked and disabled", () => {
    renderForm();
    const locked = screen.getByRole("checkbox", { name: /full name/i });
    expect(locked).toBeDisabled();
    expect(locked).toBeChecked();
    expect(screen.getByText(/always required/i)).toBeInTheDocument();
  });

  it("saves only the non-locked toggles", async () => {
    putKycRequirements.mockResolvedValue({ data: initial, error: undefined });
    renderForm();

    await userEvent.click(screen.getByRole("checkbox", { name: /phone/i }));
    await userEvent.click(screen.getByRole("checkbox", { name: /occupation/i }));
    await userEvent.click(screen.getByRole("button", { name: /save requirements/i }));

    await waitFor(() => expect(putKycRequirements).toHaveBeenCalledTimes(1));
    expect(putKycRequirements).toHaveBeenCalledWith({
      required: { phone: false, occupation: true },
    });
  });
});
