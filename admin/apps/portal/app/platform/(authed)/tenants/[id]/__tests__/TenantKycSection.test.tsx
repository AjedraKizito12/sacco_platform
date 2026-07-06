import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { OrganizationKycOut } from "@sacco/schemas";

const verifyTenant = vi.fn();
const unverifyTenant = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { kyc: { verifyTenant, unverifyTenant } } }),
}));

import { TenantKycSection } from "../_components/TenantKycSection";

function makeKyc(overrides: Partial<OrganizationKycOut> = {}): OrganizationKycOut {
  return {
    values: {
      legal_name: "Kampala Teachers SACCO",
      registration_number: "REG-001",
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
        { key: "registration_number", label: "Registration number", required: true, present: true },
      ],
      required_total: 2,
      required_present: 2,
      percent: 100,
      missing_required: [],
      is_complete: true,
    },
    ...overrides,
  };
}

function renderSection(initial: OrganizationKycOut, canVerify = true) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantKycSection tenantId="t1" initial={initial} canVerify={canVerify} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("TenantKycSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("disables Verify while incomplete and explains why", () => {
    const incomplete = makeKyc();
    incomplete.completion = {
      ...incomplete.completion,
      required_present: 1,
      percent: 50,
      missing_required: ["registration_number"],
      is_complete: false,
    };
    renderSection(incomplete);
    expect(screen.getByRole("button", { name: /^verify$/i })).toBeDisabled();
    expect(screen.getByText(/1 required item.* still missing/i)).toBeInTheDocument();
  });

  it("verifies via ConfirmDialog and flips to the verified state", async () => {
    const verified = makeKyc({
      verified: true,
      verified_at: "2026-07-07T08:00:00Z",
      verified_by_platform_user_id: "pu-1",
    });
    verifyTenant.mockResolvedValue({ data: verified, error: undefined });

    renderSection(makeKyc());
    await userEvent.click(screen.getByRole("button", { name: /^verify$/i }));
    // Direct operation — plain ConfirmDialog, no maker-checker copy.
    expect(screen.queryByText(/approval request/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /verify organization kyc/i }));

    await waitFor(() => expect(verifyTenant).toHaveBeenCalledWith("t1"));
    await waitFor(() =>
      expect(screen.getByText(/verified by platform/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /remove verification/i })).toBeInTheDocument();
  });

  it("hides the actions entirely without the write permission", () => {
    renderSection(makeKyc(), false);
    expect(screen.queryByRole("button", { name: /^verify$/i })).not.toBeInTheDocument();
  });
});
