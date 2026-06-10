import type { Meta, StoryObj } from "@storybook/react";
import { Percentage } from "./Percentage";

const meta: Meta<typeof Percentage> = {
  title: "Display/Percentage",
  component: Percentage,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof Percentage>;

export const Default: Story = { args: { value: "12.5" } };
export const Zero: Story = { args: { value: "0" } };
export const HighPrecision: Story = { args: { value: "12.345" } };
