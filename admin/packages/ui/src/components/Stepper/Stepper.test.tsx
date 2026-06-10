import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Stepper } from "./Stepper";

const steps = [
  { id: "personal", label: "Personal" },
  { id: "employment", label: "Employment" },
  { id: "documents", label: "Documents" },
];

describe("Stepper", () => {
  it("marks the current step with aria-current=step", () => {
    render(<Stepper steps={steps} currentStepId="employment" />);
    const current = screen.getByText("Employment").closest("li");
    expect(current).toHaveAttribute("aria-current", "step");
  });

  it("makes completed steps clickable + upcoming steps not", async () => {
    const onStepClick = vi.fn();
    const user = userEvent.setup();
    render(
      <Stepper
        steps={steps}
        currentStepId="employment"
        onStepClick={onStepClick}
      />,
    );
    await user.click(screen.getByText("Personal"));
    expect(onStepClick).toHaveBeenCalledWith("personal");

    await user.click(screen.getByText("Documents"));
    // Upcoming click should not fire the callback (button is disabled).
    expect(onStepClick).toHaveBeenCalledTimes(1);
  });
});
