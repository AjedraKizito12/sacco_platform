import type { Meta, StoryObj } from "@storybook/react";
import { StatusBadge, type StatusBadgeProps } from "./StatusBadge";
import {
  APPROVAL_REQUEST_STATUS,
  FEE_ASSESSMENT_STATUS,
  INVOICE_STATUS,
  LOAN_STATUS,
  MEMBER_STATUS,
  PAYMENT_STATUS,
  SAVINGS_ACCOUNT_STATUS,
  SUBSCRIPTION_STATUS,
  TENANT_STATUS,
} from "./status-maps";

const meta: Meta<typeof StatusBadge> = {
  title: "Display/StatusBadge",
  component: StatusBadge,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof StatusBadge>;

function row(
  map: Record<string, unknown>,
  entity: StatusBadgeProps["entity"],
) {
  return (
    <div className="flex flex-wrap gap-2">
      {Object.keys(map).map((status) => (
        <StatusBadge key={status} entity={entity} status={status} />
      ))}
    </div>
  );
}

export const Loan: Story = { render: () => row(LOAN_STATUS, "loan") };
export const Member: Story = { render: () => row(MEMBER_STATUS, "member") };
export const Tenant: Story = { render: () => row(TENANT_STATUS, "tenant") };
export const SavingsAccount: Story = {
  render: () => row(SAVINGS_ACCOUNT_STATUS, "savings_account"),
};
export const FeeAssessment: Story = {
  render: () => row(FEE_ASSESSMENT_STATUS, "fee_assessment"),
};
export const ApprovalRequest: Story = {
  render: () => row(APPROVAL_REQUEST_STATUS, "approval_request"),
};
export const Subscription: Story = {
  render: () => row(SUBSCRIPTION_STATUS, "subscription"),
};
export const Invoice: Story = { render: () => row(INVOICE_STATUS, "invoice") };
export const Payment: Story = { render: () => row(PAYMENT_STATUS, "payment") };
