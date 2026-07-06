import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { OrganizationKycOut } from "@sacco/schemas";

const putKyc = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { organization: { putKyc } } }),
}));

import { OrganizationKycScreen } from "../_components/OrganizationKycScreen";

function makeKyc(overrides: Partial<OrganizationKycOut> = {}): OrganizationKycOut {
  return {
    values: {
      legal_name: "Kampala Teachers SACCO",
      registration_number: null,
      registered_address: null,
      primary_contact_name: null,
      primary_contact_email: null,
      registration_date: null,
      regulator_name: null,
      license_number: null,
      tax_id: null,
      primary_contact_phone: null,
      postal_address: null,
      district_region: null,
      country: null,
    },
    verified: false,
    verified_at: null,
    verified_by_platform_user_id: null,
    completion: {
      items: [
        { key: "legal_name", label: "Registered legal name", required: true, present: true },
        { key: "registration_number", label: "Registration number", required: true, present: false },
      ],
      required_total: 2,
      required_present: 1,
      percent: 50,
      missing_required: ["registration_number"],
      is_complete: false,
    },
    ...overrides,
  };
}

function renderScreen(initial = makeKyc()) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <OrganizationKycScreen initial={initial} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("OrganizationKycScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("pre-fills values, shows the not-verified badge and completion card", () => {
    renderScreen();
    expect(screen.getByDisplayValue("Kampala Teachers SACCO")).toBeInTheDocument();
    expect(screen.getByText(/not verified/i)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
  });

  it("submits with blanks normalised to null and re-renders the returned completion", async () => {
    const next = makeKyc();
    next.values.registration_number = "REG-001";
    next.completion = {
      ...next.completion,
      required_present: 2,
      percent: 100,
      missing_required: [],
      is_complete: true,
      items: next.completion.items.map((i) => ({ ...i, present: true })),
    };
    putKyc.mockResolvedValue({ data: next, error: undefined });

    renderScreen();
    await userEvent.type(screen.getByLabelText(/registration number/i), "REG-001");
    await userEvent.click(screen.getByRole("button", { name: /save organization kyc/i }));

    await waitFor(() => expect(putKyc).toHaveBeenCalledTimes(1));
    const payload = putKyc.mock.calls[0]?.[0] as Record<string, string | null>;
    expect(payload["registration_number"]).toBe("REG-001");
    expect(payload["country"]).toBeNull(); // blank → null, never ""
    await waitFor(() =>
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100"),
    );
  });

  it("tells the operator when a save resets platform verification", async () => {
    const reset = makeKyc(); // server resets verified on material change
    putKyc.mockResolvedValue({ data: reset, error: undefined });
    renderScreen(makeKyc({ verified: true, verified_at: "2026-07-01T00:00:00Z" }));

    expect(screen.getByText(/verified by platform/i)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/regulator/i), "UMRA");
    await userEvent.click(screen.getByRole("button", { name: /save organization kyc/i }));
    await waitFor(() =>
      expect(screen.getByText(/reset platform verification/i)).toBeInTheDocument(),
    );
  });
});
