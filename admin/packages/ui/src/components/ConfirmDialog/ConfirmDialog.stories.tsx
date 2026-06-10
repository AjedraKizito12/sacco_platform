import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { Button } from "../Button";
import {
  ConfirmDialog,
  MakerCheckerConfirmDialog,
} from "./ConfirmDialog";

const meta: Meta = {
  title: "Forms/ConfirmDialog",
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj;

function Plain() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Delete member</Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Delete this member?"
        description="This is irreversible."
        confirmLabel="Delete"
        destructive
        onConfirm={() => setOpen(false)}
      />
    </>
  );
}

function MakerChecker() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Request disbursement</Button>
      <MakerCheckerConfirmDialog
        open={open}
        onOpenChange={setOpen}
        operationLabel="loan disbursement"
        subjectLabel="loan #L-2026-001234"
        onConfirm={() => setOpen(false)}
      />
    </>
  );
}

export const Destructive: Story = { render: () => <Plain /> };
export const MakerCheckerVariant: Story = { render: () => <MakerChecker /> };
