import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { DateInput } from "./DateInput";
import { DateRangeInput, type DateRangeValue } from "./DateRangeInput";

const meta: Meta<typeof DateInput> = {
  title: "Forms/DateInput",
  component: DateInput,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj;

function Single() {
  const [v, set] = useState("");
  return (
    <div style={{ width: 260 }}>
      <DateInput value={v} onValueChange={set} aria-label="date" />
      <p style={{ marginTop: 8, fontSize: 12 }}>state: {JSON.stringify(v)}</p>
    </div>
  );
}

function Range() {
  const [v, set] = useState<DateRangeValue>({ from: "", to: "" });
  return (
    <div>
      <DateRangeInput value={v} onValueChange={set} />
      <p style={{ marginTop: 8, fontSize: 12 }}>state: {JSON.stringify(v)}</p>
    </div>
  );
}

export const Single_: Story = { name: "Single", render: () => <Single /> };
export const RangeTwoMonth: Story = { render: () => <Range /> };
