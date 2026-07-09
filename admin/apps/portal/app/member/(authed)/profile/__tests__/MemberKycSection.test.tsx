import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { MemberSelfKycOut } from "@sacco/schemas";

const submitKyc = vi.fn().mockResolvedValue({ data: { id: "s1", status: "pending" } });

vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { member: { submitKyc } } }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

import { MemberKycSection } from "../_components/MemberKycSection";

const EMPTY_VALUES = {
  phone: null,
  email: null,
  physical_address: null,
  national_id_number: null,
  id_document_type: null,
  id_document_number: null,
  id_issued_date: null,
  id_expiry_date: null,
  next_of_kin_name: null,
  next_of_kin_phone: null,
  occupation: null,
};

function baseKyc(overrides: Partial<MemberSelfKycOut> = {}): MemberSelfKycOut {
  return {
    completion: {
      items: [{ key: "phone", label: "Phone", required: true, present: false }],
      required_total: 1,
      required_present: 0,
      percent: 0,
      missing_required: ["phone"],
      is_complete: false,
    },
    values: EMPTY_VALUES,
    latest_submission: null,
    ...overrides,
  };
}

function renderSection(initial: MemberSelfKycOut) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemberKycSection initial={initial} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("MemberKycSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("shows the complete-your-KYC CTA when there is no submission", () => {
    renderSection(baseKyc());
    expect(screen.getByRole("button", { name: /complete kyc/i })).toBeInTheDocument();
  });

  it("shows under-review and hides the submit button while pending", () => {
    renderSection(
      baseKyc({
        latest_submission: {
          id: "s1",
          member_id: "m1",
          status: "pending",
          submitted_at: "2026-07-08T10:00:00Z",
          reviewed_at: null,
          rejection_reason: null,
          proposed: EMPTY_VALUES,
        },
      }),
    );
    expect(screen.getByText(/under review/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /kyc/i })).not.toBeInTheDocument();
  });

  it("shows the rejection reason and a resubmit button when rejected", () => {
    renderSection(
      baseKyc({
        latest_submission: {
          id: "s1",
          member_id: "m1",
          status: "rejected",
          submitted_at: "2026-07-08T10:00:00Z",
          reviewed_at: "2026-07-08T11:00:00Z",
          rejection_reason: "ID number looks wrong",
          proposed: EMPTY_VALUES,
        },
      }),
    );
    expect(screen.getByText("ID number looks wrong")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /resubmit kyc/i })).toBeInTheDocument();
  });

  it("opens the form dialog and submits the payload", async () => {
    const user = userEvent.setup();
    renderSection(baseKyc());
    await user.click(screen.getByRole("button", { name: /complete kyc/i }));
    await user.type(screen.getByLabelText("Phone", { exact: true }), "+256700000001");
    await user.click(screen.getByRole("button", { name: /submit for review/i }));
    expect(submitKyc).toHaveBeenCalledWith(
      expect.objectContaining({ phone: "+256700000001" }),
    );
  });
});
