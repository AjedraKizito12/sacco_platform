import type { Meta, StoryObj } from "@storybook/react";
import { AuditBar } from "./AuditBar";

const meta: Meta<typeof AuditBar> = {
  title: "Forms/AuditBar",
  component: AuditBar,
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof AuditBar>;

export const Placeholder: Story = {
  args: { entityType: "loan", entityId: "L-2026-001234" },
};
