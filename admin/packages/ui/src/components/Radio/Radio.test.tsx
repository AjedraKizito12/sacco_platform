import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { RadioGroup, RadioGroupItem } from "./Radio";

describe("RadioGroup", () => {
  it("selects an item on click", async () => {
    const user = userEvent.setup();
    render(
      <RadioGroup defaultValue="one">
        <RadioGroupItem value="one" aria-label="one" />
        <RadioGroupItem value="two" aria-label="two" />
      </RadioGroup>,
    );
    const second = screen.getByRole("radio", { name: "two" });
    await user.click(second);
    expect(second).toHaveAttribute("aria-checked", "true");
  });
});
