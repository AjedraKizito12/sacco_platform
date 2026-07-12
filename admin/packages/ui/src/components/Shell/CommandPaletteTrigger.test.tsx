import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CommandPaletteTrigger } from "./CommandPaletteTrigger";

describe("CommandPaletteTrigger", () => {
  it("renders with the Search… affordance and ⌘K hint", () => {
    render(<CommandPaletteTrigger onActivate={() => {}} />);
    expect(screen.getByLabelText("Open command palette")).toBeInTheDocument();
    expect(screen.getByText("Search…")).toBeInTheDocument();
  });

  it("calls onActivate when clicked", async () => {
    const onActivate = vi.fn();
    render(<CommandPaletteTrigger onActivate={onActivate} />);
    await userEvent.click(screen.getByLabelText("Open command palette"));
    expect(onActivate).toHaveBeenCalledOnce();
  });

  it("renders a disabled 'coming soon' trigger that does not activate", async () => {
    const onActivate = vi.fn();
    render(<CommandPaletteTrigger onActivate={onActivate} disabled />);
    const button = screen.getByLabelText("Search (coming soon)");
    expect(button).toBeDisabled();
    // The ⌘K hint is dropped when disabled — the shortcut isn't wired either.
    expect(screen.queryByText("K")).not.toBeInTheDocument();
    await userEvent.click(button);
    expect(onActivate).not.toHaveBeenCalled();
  });
});
