import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { PercentageInput } from "./PercentageInput";

const meta: Meta<typeof PercentageInput> = {
  title: "Forms/PercentageInput",
  component: PercentageInput,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj;

function Demo() {
  const [v, set] = useState("");
  return (
    <div style={{ width: 200 }}>
      <PercentageInput value={v} onValueChange={set} aria-label="rate" />
      <p style={{ marginTop: 8, fontSize: 12 }}>state: {JSON.stringify(v)}</p>
    </div>
  );
}

export const Default: Story = { render: () => <Demo /> };
