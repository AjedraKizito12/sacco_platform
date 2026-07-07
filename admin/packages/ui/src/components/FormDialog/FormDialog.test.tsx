import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FormDialog } from "./FormDialog";
import { FormSection } from "./FormSection";
import { Button } from "../Button";

function Harness({ onDismiss, onSubmit }: { onDismiss: () => void; onSubmit: () => void }) {
  return (
    <FormDialog
      open
      onDismiss={onDismiss}
      title="Register member"
      description="Add a new member."
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      footer={<Button type="submit">Register member</Button>}
    >
      <FormSection title="Personal details">
        <label htmlFor="name">Full name</label>
        <input id="name" />
      </FormSection>
    </FormDialog>
  );
}

describe("FormDialog", () => {
  it("renders title, description and grouped fields", async () => {
    render(<Harness onDismiss={vi.fn()} onSubmit={vi.fn()} />);
    expect(await screen.findByRole("dialog", { name: "Register member" })).toBeInTheDocument();
    expect(screen.getByText("Add a new member.")).toBeInTheDocument();
    expect(screen.getByText("Personal details")).toBeInTheDocument();
  });

  it("submits via the footer button", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onDismiss={vi.fn()} onSubmit={onSubmit} />);
    await user.click(await screen.findByRole("button", { name: "Register member" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("calls onDismiss when the close button is pressed", async () => {
    const onDismiss = vi.fn();
    const user = userEvent.setup();
    render(<Harness onDismiss={onDismiss} onSubmit={vi.fn()} />);
    await user.click(await screen.findByRole("button", { name: "Close" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
