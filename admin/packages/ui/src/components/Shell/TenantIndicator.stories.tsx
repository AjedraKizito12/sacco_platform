import type { Meta, StoryObj } from "@storybook/react";
import { TenantIndicator } from "./TenantIndicator";

const meta: Meta<typeof TenantIndicator> = {
  title: "Shell/TenantIndicator",
  component: TenantIndicator,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof TenantIndicator>;

export const Default: Story = { args: { tenantName: "Sacco One" } };
export const Impersonating: Story = {
  args: { tenantName: "Sacco Two", impersonating: true },
};
export const LongName: Story = {
  args: { tenantName: "Wakiso Teachers Cooperative Savings Society Ltd" },
};
