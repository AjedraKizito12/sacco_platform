import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { PercentageInput } from "./PercentageInput";

function Controlled({ min, max }: { min?: number; max?: number }) {
  const [v, set] = useState("");
  return (
    <div>
      <PercentageInput
        value={v}
        onValueChange={set}
        {...(min !== undefined ? { min } : {})}
        {...(max !== undefined ? { max } : {})}
        aria-label="rate"
      />
      <p data-testid="state">{v}</p>
    </div>
  );
}

describe("PercentageInput", () => {
  it("renders the % suffix", () => {
    render(<Controlled />);
    expect(screen.getByText("%")).toBeInTheDocument();
  });

  it("truncates beyond 2 decimal places", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const input = screen.getByLabelText("rate") as HTMLInputElement;
    await user.type(input, "12.345");
    expect(input.value).toBe("12.34");
  });

  it("canonicalises to 2 decimals on blur", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const input = screen.getByLabelText("rate") as HTMLInputElement;
    await user.type(input, "5");
    await user.tab();
    expect(input.value).toBe("5.00");
  });

  it("clamps to [min, max] on blur", async () => {
    const user = userEvent.setup();
    render(<Controlled min={0} max={100} />);
    const input = screen.getByLabelText("rate") as HTMLInputElement;
    await user.type(input, "150");
    await user.tab();
    expect(input.value).toBe("100.00");
  });
});
