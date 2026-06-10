import type { Meta, StoryObj } from "@storybook/react";
import { ReadOnlyField } from "./ReadOnlyField";

const meta: Meta<typeof ReadOnlyField> = {
  title: "Forms/ReadOnlyField",
  component: ReadOnlyField,
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof ReadOnlyField>;

export const Default: Story = {
  args: { label: "Member ID", value: "M-2026-0042" },
};
export const Stacked: Story = {
  render: () => (
    <div style={{ display: "grid", gap: 16, maxWidth: 320 }}>
      <ReadOnlyField label="Member ID" value="M-2026-0042" />
      <ReadOnlyField label="Joined" value="28 May 2026" />
    </div>
  ),
};
