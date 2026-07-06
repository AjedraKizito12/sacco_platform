import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { SaccoKycRequirementsOut } from "@sacco/schemas";

const putSaccoRequirements = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { kyc: { putSaccoRequirements } } }),
}));

import { SaccoKycRequirementsForm } from "../_components/SaccoKycRequirementsForm";

const initial: SaccoKycRequirementsOut = {
  items: [
    { key: "legal_name", label: "Registered legal name", locked: true, required: true },
    { key: "tax_id", label: "Tax identification number", locked: false, required: true },
    { key: "country", label: "Country", locked: false, required: false },
  ],
};

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <SaccoKycRequirementsForm initial={initial} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("SaccoKycRequirementsForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("renders locked minimums as checked and disabled", () => {
    renderForm();
    const locked = screen.getByRole("checkbox", { name: /registered legal name/i });
    expect(locked).toBeDisabled();
    expect(locked).toBeChecked();
    expect(screen.getByText(/always required/i)).toBeInTheDocument();
  });

  it("saves only the non-locked toggles", async () => {
    putSaccoRequirements.mockResolvedValue({ data: initial, error: undefined });
    renderForm();

    await userEvent.click(screen.getByRole("checkbox", { name: /tax identification/i }));
    await userEvent.click(screen.getByRole("checkbox", { name: /country/i }));
    await userEvent.click(screen.getByRole("button", { name: /save requirements/i }));

    await waitFor(() => expect(putSaccoRequirements).toHaveBeenCalledTimes(1));
    expect(putSaccoRequirements).toHaveBeenCalledWith({
      required: { tax_id: false, country: true },
    });
  });
});
