import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Input } from "./Input";

describe("Input", () => {
  it("forwards value typing", async () => {
    const user = userEvent.setup();
    render(<Input aria-label="member-name" />);
    const input = screen.getByLabelText("member-name");
    await user.type(input, "Mary Akello");
    expect(input).toHaveValue("Mary Akello");
  });

  it("applies error styling when error=true", () => {
    render(<Input aria-label="amount" error />);
    expect(screen.getByLabelText("amount").className).toMatch(/border-/);
  });
});
