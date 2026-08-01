import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const triggerVerification = vi.fn();
const refresh = vi.fn();

vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { ops: { triggerVerification } } }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh }),
}));

import { VerifyNowButton } from "../_components/VerifyNowButton";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("VerifyNowButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    triggerVerification.mockResolvedValue({
      data: { id: "v1", status: "requested" },
    });
  });

  it("opens a confirm dialog and triggers a verification on confirm", async () => {
    const user = userEvent.setup();
    render(<VerifyNowButton />, { wrapper });

    await user.click(screen.getByRole("button", { name: "Verify now" }));
    expect(
      screen.getByText("Run a restore-verify drill now?"),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Run drill" }));
    await waitFor(() => expect(triggerVerification).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("does not trigger a verification unless confirmed", async () => {
    const user = userEvent.setup();
    render(<VerifyNowButton />, { wrapper });
    await user.click(screen.getByRole("button", { name: "Verify now" }));
    expect(triggerVerification).not.toHaveBeenCalled();
  });
});
