import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { DateInput } from "./DateInput";

function Controlled({ initial = "" }: { initial?: string }) {
  const [v, set] = useState(initial);
  return (
    <div>
      <DateInput value={v} onValueChange={set} aria-label="date" />
      <p data-testid="state">{v}</p>
    </div>
  );
}

describe("DateInput", () => {
  it("hydrates from an ISO value", () => {
    render(<Controlled initial="2026-05-28" />);
    expect(screen.getByLabelText("date")).toHaveValue("28/05/2026");
  });

  it("accepts a typed DD/MM/YYYY and emits ISO", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const input = screen.getByLabelText("date") as HTMLInputElement;
    await user.type(input, "28/05/2026");
    await user.tab();
    expect(screen.getByTestId("state").textContent).toBe("2026-05-28");
  });

  it("accepts a typed YYYY-MM-DD and emits ISO", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    const input = screen.getByLabelText("date") as HTMLInputElement;
    await user.type(input, "2026-05-28");
    await user.tab();
    expect(screen.getByTestId("state").textContent).toBe("2026-05-28");
  });

  it("reverts to the last known value on garbage input", async () => {
    const user = userEvent.setup();
    render(<Controlled initial="2026-05-28" />);
    const input = screen.getByLabelText("date") as HTMLInputElement;
    await user.clear(input);
    await user.type(input, "yesterday");
    await user.tab();
    expect(input.value).toBe("28/05/2026");
  });
});
