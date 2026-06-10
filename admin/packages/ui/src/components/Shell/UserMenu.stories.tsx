import type { Meta, StoryObj } from "@storybook/react";
import { UserMenu } from "./UserMenu";

const meta: Meta<typeof UserMenu> = {
  title: "Shell/UserMenu",
  component: UserMenu,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof UserMenu>;

export const Default: Story = {
  args: {
    fullName: "Jane Operator",
    email: "jane@platform.example",
    contextLabel: "Superuser",
    onSignOut: () => {},
  },
};

export const WithProfile: Story = {
  args: {
    fullName: "Mary Operator",
    email: "mary@sacco-one.example",
    contextLabel: "Tenant Admin",
    onProfile: () => {},
    onSignOut: () => {},
  },
};
