import type { Meta, StoryObj } from "@storybook/react";
import { MakerCheckerBanner } from "./MakerCheckerBanner";

const meta: Meta<typeof MakerCheckerBanner> = {
  title: "Forms/MakerCheckerBanner",
  component: MakerCheckerBanner,
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof MakerCheckerBanner>;

const baseArgs = {
  approvalRequestId: "AR-1234",
  operationLabel: "Loan disbursement",
  requesterName: "Sarah Achieng",
  requestedAt: "28 May 2026",
  quorumRequired: 2,
  quorumCurrent: 1,
  action: (
    <a href="/approvals/AR-1234" className="text-[13px] underline">
      View Approval Request
    </a>
  ),
};

export const OneOfTwo: Story = { args: baseArgs };
export const OneOfThree: Story = {
  args: { ...baseArgs, quorumRequired: 3 },
};
