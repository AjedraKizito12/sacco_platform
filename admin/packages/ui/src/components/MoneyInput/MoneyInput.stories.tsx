import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { MoneyInput } from "./MoneyInput";
import { TenantCurrencyProvider } from "../../context/TenantCurrency";

const meta: Meta<typeof MoneyInput> = {
  title: "Forms/MoneyInput",
  component: MoneyInput,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj;

function Demo({
  currency,
  allowNegative,
}: {
  currency?: string;
  allowNegative?: boolean;
}) {
  const [value, setValue] = useState("");
  return (
    <div style={{ width: 280 }}>
      <MoneyInput
        value={value}
        onValueChange={setValue}
        {...(currency !== undefined ? { currency } : {})}
        {...(allowNegative !== undefined ? { allowNegative } : {})}
        aria-label="amount"
      />
      <p style={{ marginTop: 8, fontSize: 12 }}>state: {JSON.stringify(value)}</p>
    </div>
  );
}

export const UGX: Story = { render: () => <Demo currency="UGX" /> };
export const USD: Story = { render: () => <Demo currency="USD" /> };
export const AllowNegative: Story = {
  render: () => <Demo currency="USD" allowNegative />,
};
export const FromProvider: Story = {
  render: () => (
    <TenantCurrencyProvider currency="KES">
      <Demo />
    </TenantCurrencyProvider>
  ),
};
