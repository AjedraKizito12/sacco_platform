import type { Meta, StoryObj } from "@storybook/react";
import { Money } from "./Money";

const meta: Meta<typeof Money> = {
  title: "Display/Money",
  component: Money,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof Money>;

export const UGX: Story = { args: { amount: "1234567", currency: "UGX" } };
export const KES: Story = { args: { amount: "50000.50", currency: "KES" } };
export const USD: Story = { args: { amount: "12.34", currency: "USD" } };
export const Zero: Story = { args: { amount: "0", currency: "UGX" } };
export const Negative: Story = { args: { amount: "-1234567", currency: "UGX" } };
export const Large: Story = {
  args: { amount: "12345000", currency: "UGX", size: "large" },
};

export const TableAlignmentDemo: Story = {
  render: () => (
    <table className="border-collapse">
      <tbody>
        {["1234", "1234567", "1234567890", "12.34"].map((v) => (
          <tr key={v} className="border-b">
            <td className="px-4 py-2 text-right">
              <Money amount={v} currency="UGX" />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  ),
};
