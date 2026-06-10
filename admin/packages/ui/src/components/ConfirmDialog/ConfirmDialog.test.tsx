import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ConfirmDialog,
  MakerCheckerConfirmDialog,
} from "./ConfirmDialog";

describe("ConfirmDialog", () => {
  it("renders title + description + confirm/cancel", () => {
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="Delete member?"
        description="This cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={() => {}}
      />,
    );
    expect(screen.getByText("Delete member?")).toBeInTheDocument();
    expect(screen.getByText("This cannot be undone.")).toBeInTheDocument();
    expect(screen.getByText("Delete")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
  });

  it("calls onConfirm when confirm clicked", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="Proceed?"
        confirmLabel="Yes"
        onConfirm={onConfirm}
      />,
    );
    await user.click(screen.getByText("Yes"));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("disables both buttons when busy", () => {
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="Proceed?"
        confirmLabel="Yes"
        onConfirm={() => {}}
        busy
      />,
    );
    expect(screen.getByText("Yes")).toBeDisabled();
    expect(screen.getByText("Cancel")).toBeDisabled();
  });
});

describe("MakerCheckerConfirmDialog", () => {
  it("locks the spec copy (line 1102)", () => {
    render(
      <MakerCheckerConfirmDialog
        open
        onOpenChange={() => {}}
        operationLabel="loan disbursement"
        subjectLabel="loan #L-2026-001234"
        onConfirm={() => {}}
      />,
    );
    expect(
      screen.getByText(/This will create an approval request, not execute/),
    ).toBeInTheDocument();
    expect(screen.getByText("Create Approval Request")).toBeInTheDocument();
    expect(
      screen.getByText("Request loan disbursement on loan #L-2026-001234"),
    ).toBeInTheDocument();
  });
});
