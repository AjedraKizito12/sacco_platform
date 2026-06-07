import type { Meta, StoryObj } from "@storybook/react";
import { Input } from "./Input";

const meta: Meta<typeof Input> = {
  title: "Primitives/Input",
  component: Input,
  parameters: { layout: "padded" },
};
export default meta;

type Story = StoryObj<typeof Input>;

export const Default: Story = { args: { placeholder: "e.g. Mary Akello" } };
export const Hover: Story = { args: { placeholder: "hover state (via :hover)" } };
export const Focus: Story = {
  args: { placeholder: "tab to me", autoFocus: true },
};
export const Disabled: Story = { args: { disabled: true, value: "disabled" } };
export const ReadOnly: Story = {
  args: { readOnly: true, value: "read-only informational" },
};
export const Error: Story = {
  args: { error: true, value: "invalid amount" },
};
export const Success: Story = {
  args: { success: true, value: "available" },
};

export const Grid: Story = {
  render: () => (
    <div className="flex max-w-md flex-col gap-3">
      <Input placeholder="Default" />
      <Input placeholder="Disabled" disabled />
      <Input value="Read-only" readOnly />
      <Input value="Error" error onChange={() => {}} />
      <Input value="Success" success onChange={() => {}} />
    </div>
  ),
};
