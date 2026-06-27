import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));
const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

import { LoginForm } from "../LoginForm";

beforeEach(() => {
  push.mockClear();
  fetchMock.mockReset();
});

describe("LoginForm (member)", () => {
  it("member variant posts to /api/auth/member-login and redirects to dashboard", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: "a", expires_in: 900 }),
    });
    render(<LoginForm variant="member" />);
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "jane@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "S3cret-pass!ok" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/auth/member-login",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/member/dashboard"));
  });
});
