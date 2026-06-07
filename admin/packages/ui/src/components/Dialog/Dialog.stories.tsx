import type { Meta, StoryObj } from "@storybook/react";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogClose,
} from "./Dialog";
import { Button } from "../Button";

const meta: Meta<typeof Dialog> = {
  title: "Overlays/Dialog",
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof Dialog>;

export const ConfirmAction: Story = {
  render: () => (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="destructive">Request reversal</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reverse transaction TXN-2026-0042</DialogTitle>
          <DialogDescription>
            This creates an approval request, not executes. Another authorized user must approve
            before the reversal posts.
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          <p className="text-[var(--text-secondary)]">
            Provide a reason for the reversal so the checker has context.
          </p>
        </DialogBody>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="secondary">Cancel</Button>
          </DialogClose>
          <Button variant="destructive">Create approval request</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  ),
};
