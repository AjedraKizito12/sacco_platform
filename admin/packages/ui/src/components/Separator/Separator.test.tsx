import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Separator } from "./Separator";

describe("Separator", () => {
  it("renders as a horizontal divider by default", () => {
    const { container } = render(<Separator />);
    expect(container.firstChild).toHaveAttribute("data-orientation", "horizontal");
  });
});
