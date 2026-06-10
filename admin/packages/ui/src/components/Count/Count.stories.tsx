import type { Meta, StoryObj } from "@storybook/react";
import { Count } from "./Count";

const meta: Meta<typeof Count> = {
  title: "Display/Count",
  component: Count,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof Count>;

export const Default: Story = { args: { value: 1234 } };
export const Large: Story = { args: { value: 1234567890 } };
