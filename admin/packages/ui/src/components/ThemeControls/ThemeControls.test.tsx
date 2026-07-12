import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeControls, ThemeModeToggle } from "./ThemeControls";

const base = { mode: "system", accent: "default", fontSize: "default" } as const;

describe("ThemeControls", () => {
  it("marks the current mode/accent/size selected", () => {
    render(<ThemeControls value={{ ...base, mode: "dark", accent: "blue" }} onChange={() => {}} />);
    expect(screen.getByRole("button", { name: /dark/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /blue/i })).toHaveAttribute("aria-pressed", "true");
  });
  it("fires onChange with the updated mode", async () => {
    const onChange = vi.fn();
    render(<ThemeControls value={base} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /dark/i }));
    expect(onChange).toHaveBeenCalledWith({ ...base, mode: "dark" });
  });
  it("fires onChange with the updated accent", async () => {
    const onChange = vi.fn();
    render(<ThemeControls value={base} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /green/i }));
    expect(onChange).toHaveBeenCalledWith({ ...base, accent: "green" });
  });
  it("fires onChange with the updated font size", async () => {
    const onChange = vi.fn();
    render(<ThemeControls value={base} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /large/i }));
    expect(onChange).toHaveBeenCalledWith({ ...base, fontSize: "large" });
  });
});

describe("ThemeModeToggle", () => {
  it("cycles light → dark", async () => {
    const onChange = vi.fn();
    render(<ThemeModeToggle value="light" onChange={onChange} />);
    await userEvent.click(screen.getByRole("button"));
    expect(onChange).toHaveBeenCalledWith("dark");
  });
});
