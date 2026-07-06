import type { Meta, StoryObj } from "@storybook/react";
import { ChartCard } from "./ChartCard";
import { TrendAreaChart } from "./TrendAreaChart";
import { CompositionDonut } from "./CompositionDonut";
import { CompositionBar } from "./CompositionBar";

const meta: Meta = {
  title: "Charts/Dashboard",
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj;

const TREND = [
  { label: "Jan", value: 4_200_000 },
  { label: "Feb", value: 4_600_000 },
  { label: "Mar", value: 5_100_000 },
  { label: "Apr", value: 5_050_000 },
  { label: "May", value: 5_900_000 },
  { label: "Jun", value: 6_400_000 },
];

const LOANS = [
  { label: "Disbursed", value: 42 },
  { label: "In arrears", value: 9 },
  { label: "Closed", value: 18 },
  { label: "Written off", value: 3 },
];

export const Trend: Story = {
  render: () => (
    <div className="max-w-[640px]">
      <ChartCard title="Savings growth" subtitle="Last 6 months" seeAllHref="#">
        <TrendAreaChart
          data={TREND}
          ariaLabel="Savings growth"
          valueFormat={{ kind: "money", currency: "UGX" }}
        />
      </ChartCard>
    </div>
  ),
};

export const Donut: Story = {
  render: () => (
    <div className="max-w-[480px]">
      <ChartCard title="Loans by status" seeAllHref="#">
        <CompositionDonut data={LOANS} />
      </ChartCard>
    </div>
  ),
};

export const Bar: Story = {
  render: () => (
    <div className="max-w-[480px]">
      <ChartCard title="Members by status">
        <CompositionBar
          data={[
            { label: "Active", value: 320 },
            { label: "Pending", value: 44 },
            { label: "Suspended", value: 12 },
            { label: "Exited", value: 7 },
          ]}
        />
      </ChartCard>
    </div>
  ),
};

export const EmptyStates: Story = {
  render: () => (
    <div className="grid max-w-[720px] grid-cols-2 gap-4">
      <ChartCard title="Savings growth">
        <TrendAreaChart data={[]} ariaLabel="Savings growth" />
      </ChartCard>
      <ChartCard title="Loans by status">
        <CompositionDonut data={[{ label: "Disbursed", value: 0 }]} />
      </ChartCard>
    </div>
  ),
};
