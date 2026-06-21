// admin/apps/portal/src/__tests__/tenant-credit/GuarantorsSection.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";
import type { GuarantorOut } from "@sacco/schemas";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const addGuarantor = vi.fn();
const acceptGuarantor = vi.fn();
const declineGuarantor = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({
    resources: { credit: { addGuarantor, acceptGuarantor, declineGuarantor } },
  }),
}));

import {
  GuarantorsSection,
  type MemberOption,
} from "../../../app/(tenant-authed)/credit/applications/[id]/_components/GuarantorsSection";

const M2 = "550e8400-e29b-41d4-a716-446655440002";
const M3 = "550e8400-e29b-41d4-a716-446655440003";
const guarantors: GuarantorOut[] = [
  {
    id: "g1",
    loan_application_id: "a1",
    guarantor_member_id: M2,
    guaranteed_amount: "500000.00",
    status: "pending",
    consented_at: null,
  },
];
const members: MemberOption[] = [
  { id: M2, full_name: "Ben Okello", member_number: "M-0002" },
  { id: M3, full_name: "Cara N", member_number: "M-0003" },
];

function renderSection() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <GuarantorsSection applicationId="a1" guarantors={guarantors} members={members} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("GuarantorsSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("renders a guarantor row with member label and status", () => {
    renderSection();
    expect(screen.getByText("Ben Okello (M-0002)")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("accepts a guarantor with its member id", async () => {
    acceptGuarantor.mockResolvedValue({ data: { id: "g1" }, error: undefined });
    renderSection();
    await userEvent.click(screen.getByRole("button", { name: "Accept" }));
    const confirm = await screen.findAllByRole("button", { name: "Accept" });
    await userEvent.click(confirm[confirm.length - 1]!);
    expect(await screen.findByText(/guarantor accepted/i)).toBeInTheDocument();
    expect(acceptGuarantor).toHaveBeenCalledWith("g1", { guarantor_member_id: M2 });
  });

  it("nominates a member not already a guarantor", async () => {
    addGuarantor.mockResolvedValue({ data: [{ id: "g2" }], error: undefined });
    renderSection();
    await userEvent.click(screen.getByRole("button", { name: /add guarantor/i }));
    // Only Cara (m3) is selectable — Ben (m2) is already a guarantor.
    // Only Cara (m3) is selectable — Ben (m2) is already a guarantor.
    expect(screen.getByText("Cara N (M-0003)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: /add selected/i }));
    expect(await screen.findByText(/guarantors added/i)).toBeInTheDocument();
    expect(addGuarantor).toHaveBeenCalledWith("a1", { guarantor_member_ids: [M3] });
  });
});
