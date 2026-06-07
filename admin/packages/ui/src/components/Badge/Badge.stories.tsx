import type { Meta, StoryObj } from "@storybook/react";
import { Badge } from "./Badge";

const meta: Meta<typeof Badge> = {
  title: "Primitives/Badge",
  component: Badge,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof Badge>;

const VARIANTS = [
  "success",
  "warning",
  "danger",
  "danger-solid",
  "info",
  "neutral",
  "dark",
  "accent",
] as const;

export const All: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      {VARIANTS.map((variant) => (
        <Badge key={variant} variant={variant}>
          {variant}
        </Badge>
      ))}
    </div>
  ),
};

export const WithDot: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      {VARIANTS.map((variant) => (
        <Badge key={variant} variant={variant} withDot>
          {variant}
        </Badge>
      ))}
    </div>
  ),
};

export const DomainLoanStatuses: Story = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <Badge variant="neutral">Draft</Badge>
      <Badge variant="info">Submitted</Badge>
      <Badge variant="success">Approved</Badge>
      <Badge variant="warning">Disbursing</Badge>
      <Badge variant="danger-solid">In Arrears</Badge>
      <Badge variant="accent">Restructured</Badge>
      <Badge variant="dark">Closed</Badge>
    </div>
  ),
};
