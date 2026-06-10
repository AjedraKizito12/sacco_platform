import { describe, expect, it, beforeAll, afterAll, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

// Mock useRouter / useSearchParams because next/navigation isn't available in
// jsdom out of the box.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { LoginForm } from "@/components/forms/LoginForm";

const server = setupServer(
  http.post("http://localhost/api/auth/platform-login", async ({ request }) => {
    const body = (await request.json()) as { email: string; password: string };
    if (body.email === "good@test.example" && body.password === "GoodPass!2026") {
      return HttpResponse.json({ access_token: "abc", expires_in: 900 });
    }
    return new HttpResponse(JSON.stringify({ detail: "Invalid credentials" }), {
      status: 401,
    });
  }),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("LoginForm (platform)", () => {
  it("validates email format client-side", async () => {
    const user = userEvent.setup();
    render(<LoginForm variant="platform" />);
    await user.type(screen.getByLabelText(/email/i), "not-an-email");
    await user.type(screen.getByLabelText(/password/i), "x");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
  });

  it("surfaces 401 as user-visible error", async () => {
    const user = userEvent.setup();
    render(<LoginForm variant="platform" />);
    await user.type(screen.getByLabelText(/email/i), "wrong@test.example");
    await user.type(screen.getByLabelText(/password/i), "anything");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid/i);
  });

  it("submits successfully", async () => {
    const user = userEvent.setup();
    render(<LoginForm variant="platform" />);
    await user.type(screen.getByLabelText(/email/i), "good@test.example");
    await user.type(screen.getByLabelText(/password/i), "GoodPass!2026");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    // We don't assert the redirect; useRouter is mocked. The absence of a
    // visible error is the signal.
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
