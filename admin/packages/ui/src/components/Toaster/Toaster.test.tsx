import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Toaster } from "./Toaster";

describe("Toaster", () => {
  it("renders without crashing", () => {
    const { container } = render(<Toaster />);
    expect(container).toBeTruthy();
  });
});
