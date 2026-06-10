import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { NotificationBellStub } from "./NotificationBellStub";

describe("NotificationBellStub", () => {
  it("renders a disabled bell with the 'coming soon' aria label", () => {
    render(<NotificationBellStub />);
    const button = screen.getByLabelText("Notifications (coming soon)");
    expect(button).toBeInTheDocument();
    expect(button).toBeDisabled();
  });
});
