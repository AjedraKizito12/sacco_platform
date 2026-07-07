import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { Button } from "../Button";
import { Input } from "../Input";
import { Label } from "../Label";
import { FormDialog } from "./FormDialog";
import { FormSection } from "./FormSection";

const meta: Meta = {
  title: "Forms/FormDialog",
  parameters: { layout: "fullscreen" },
};
export default meta;
type Story = StoryObj;

function Demo() {
  const [open, setOpen] = useState(true);
  return (
    <div className="min-h-screen bg-[var(--surface-base)] p-10">
      <Button onClick={() => setOpen(true)}>Register member</Button>
      <FormDialog
        open={open}
        onDismiss={() => setOpen(false)}
        title="Register member"
        description="Add a new member to the SACCO."
        onSubmit={(e) => {
          e.preventDefault();
          setOpen(false);
        }}
        footer={
          <>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit">Register member</Button>
          </>
        }
      >
        <FormSection title="Personal details" columns={2}>
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="fd-name">Full name</Label>
            <Input id="fd-name" placeholder="Jane Doe" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="fd-dob">Date of birth</Label>
            <Input id="fd-dob" type="date" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="fd-phone">Phone</Label>
            <Input id="fd-phone" type="tel" placeholder="+256…" />
          </div>
        </FormSection>
        <FormSection title="Contact" columns={2}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="fd-email">Email</Label>
            <Input id="fd-email" type="email" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="fd-address">Physical address</Label>
            <Input id="fd-address" />
          </div>
        </FormSection>
      </FormDialog>
    </div>
  );
}

export const Default: Story = { render: () => <Demo /> };
