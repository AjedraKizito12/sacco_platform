import type { Meta, StoryObj } from "@storybook/react";
import { Card, CardBody, CardFooter, CardHeader, KpiCard } from "./Card";

const meta: Meta<typeof Card> = {
  title: "Surfaces/Card",
  component: Card,
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof Card>;

export const Standard: Story = {
  render: () => (
    <Card className="max-w-md">
      <p className="mb-1 text-sm font-medium text-[var(--text-tertiary)]">Member ID</p>
      <p className="text-base text-[var(--text-primary)]">M-2026-0001</p>
    </Card>
  ),
};

export const Sectioned: Story = {
  render: () => (
    <Card className="max-w-lg p-0">
      <CardHeader>
        <h3 className="text-[18px] font-semibold">Savings account</h3>
      </CardHeader>
      <CardBody>Account #SA-2026-0042 · Current balance UGX 1,234,567</CardBody>
      <CardFooter>Last updated 2 hours ago</CardFooter>
    </Card>
  ),
};

export const KpiTriad: Story = {
  render: () => (
    <div className="grid max-w-3xl grid-cols-3 gap-4">
      <KpiCard
        label="Total Members"
        value="1,234"
        trend={{ direction: "up", label: "+5.2% MoM" }}
      />
      <KpiCard
        label="Outstanding Loans"
        value="UGX 12,345,000"
        trend={{ direction: "down", label: "-1.4% MoM" }}
      />
      <KpiCard
        label="Members in Arrears"
        value="14"
        trend={{ direction: "flat", label: "no change" }}
      />
    </div>
  ),
};
