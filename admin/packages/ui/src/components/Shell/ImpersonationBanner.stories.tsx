import type { Meta, StoryObj } from "@storybook/react";
import { ImpersonationBanner } from "./ImpersonationBanner";

const meta: Meta<typeof ImpersonationBanner> = {
  title: "Shell/ImpersonationBanner",
  component: ImpersonationBanner,
  args: {
    tenantName: "Kampala Teachers SACCO",
    expiresAt: "2026-06-13T12:30:00Z",
    onEnd: () => {},
  },
};
export default meta;
type Story = StoryObj<typeof ImpersonationBanner>;

export const Default: Story = {};
export const Busy: Story = { args: { busy: true } };
