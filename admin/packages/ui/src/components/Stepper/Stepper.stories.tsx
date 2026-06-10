import type { Meta, StoryObj } from "@storybook/react";
import { Stepper } from "./Stepper";

const meta: Meta<typeof Stepper> = {
  title: "Forms/Stepper",
  component: Stepper,
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof Stepper>;

const steps = [
  { id: "personal", label: "Personal" },
  { id: "employment", label: "Employment" },
  { id: "documents", label: "Documents" },
  { id: "review", label: "Review" },
];

export const Mid: Story = {
  args: { steps, currentStepId: "documents" },
};
export const Start: Story = {
  args: { steps, currentStepId: "personal" },
};
export const End: Story = {
  args: { steps, currentStepId: "review" },
};
