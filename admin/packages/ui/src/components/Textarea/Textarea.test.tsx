import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Textarea } from "./Textarea";

describe("Textarea", () => {
  it("accepts multi-line text", async () => {
    const user = userEvent.setup();
    render(<Textarea aria-label="reason" />);
    const ta = screen.getByLabelText("reason");
    await user.type(ta, "Investigating reported balance issue");
    expect(ta).toHaveValue("Investigating reported balance issue");
  });
});
