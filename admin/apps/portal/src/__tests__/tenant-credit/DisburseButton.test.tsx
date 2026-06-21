// admin/apps/portal/src/__tests__/tenant-credit/DisburseButton.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const disburse = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { credit: { disburse } } }),
}));

import { DisburseButton } from "../../../app/(tenant-authed)/credit/applications/[id]/_components/DisburseButton";

function renderButton() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <DisburseButton applicationId="a1" />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("DisburseButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("disburses via a confirm dialog and redirects to the loan", async () => {
    disburse.mockResolvedValue({ data: { id: "l9" }, error: undefined });
    renderButton();
    await userEvent.click(screen.getByRole("button", { name: "Disburse" }));
    const confirmButtons = await screen.findAllByRole("button", { name: "Disburse" });
    await userEvent.click(confirmButtons[confirmButtons.length - 1]!);

    expect(await screen.findByText(/loan disbursed/i)).toBeInTheDocument();
    expect(disburse).toHaveBeenCalledWith(
      "a1",
      expect.objectContaining({ idempotency_key: expect.any(String) }),
    );
    expect(push).toHaveBeenCalledWith("/credit/loans/l9");
  });
});
