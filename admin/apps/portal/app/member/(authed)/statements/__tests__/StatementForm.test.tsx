import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StatementForm } from "../_components/StatementForm";

const openSpy = vi.fn();

beforeEach(() => {
  openSpy.mockReset();
  vi.stubGlobal("open", openSpy);
});

describe("StatementForm", () => {
  it("opens the PDF proxy URL with the chosen range", async () => {
    const user = userEvent.setup();
    render(<StatementForm />);
    await user.type(screen.getByLabelText(/from/i), "2026-01-01");
    await user.type(screen.getByLabelText(/^to/i), "2026-02-28");
    await user.click(screen.getByRole("button", { name: /download pdf/i }));
    await waitFor(() => expect(openSpy).toHaveBeenCalledTimes(1));
    const url = openSpy.mock.calls[0]![0] as string;
    expect(url).toContain("/api/member/statement?");
    expect(url).toContain("format=pdf");
    expect(url).toContain("from_date=2026-01-01");
    expect(url).toContain("to_date=2026-02-28");
  });

  it("opens the HTML preview without dates", async () => {
    const user = userEvent.setup();
    render(<StatementForm />);
    await user.click(screen.getByRole("button", { name: /preview in browser/i }));
    await waitFor(() => expect(openSpy).toHaveBeenCalledTimes(1));
    const url = openSpy.mock.calls[0]![0] as string;
    expect(url).toContain("format=html");
    expect(url).not.toContain("from_date");
  });

  it("blocks an inverted range", async () => {
    const user = userEvent.setup();
    render(<StatementForm />);
    await user.type(screen.getByLabelText(/from/i), "2026-03-01");
    await user.type(screen.getByLabelText(/^to/i), "2026-01-01");
    await user.click(screen.getByRole("button", { name: /download pdf/i }));
    expect(await screen.findByText(/before/i)).toBeInTheDocument();
    expect(openSpy).not.toHaveBeenCalled();
  });
});
