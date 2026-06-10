import type { Meta, StoryObj } from "@storybook/react";
import {
  AuditTimestamp,
  FormattedDate,
  FormattedDateTime,
  RelativeTime,
} from "./FormattedDate";

const meta: Meta = {
  title: "Display/Date",
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj;

export const FormattedDateExample: Story = {
  render: () => <FormattedDate value="2026-05-28" />,
};

export const FormattedDateTimeExample: Story = {
  render: () => <FormattedDateTime value="2026-05-28T14:32:00Z" />,
};

export const AuditTimestampExample: Story = {
  render: () => <AuditTimestamp value="2026-05-28T14:32:07Z" />,
};

export const RelativeTimeExample: Story = {
  render: () => (
    <div className="flex flex-col gap-2">
      <RelativeTime value={new Date(Date.now() - 2 * 60 * 60 * 1000)} />
      <RelativeTime value={new Date(Date.now() - 30 * 24 * 60 * 60 * 1000)} />
    </div>
  ),
};
