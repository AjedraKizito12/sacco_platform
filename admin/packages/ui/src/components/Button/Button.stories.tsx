import type { Meta, StoryObj } from "@storybook/react";
import { Button } from "./Button";

const meta: Meta<typeof Button> = {
  title: "Primitives/Button",
  component: Button,
  parameters: { layout: "centered" },
  argTypes: {
    variant: {
      control: "select",
      options: ["primary", "secondary", "ghost", "destructive"],
    },
    size: { control: "select", options: ["sm", "md", "lg"] },
    disabled: { control: "boolean" },
    asChild: { control: false },
  },
};
export default meta;

type Story = StoryObj<typeof Button>;

export const Primary: Story = { args: { variant: "primary", children: "Save member" } };
export const Secondary: Story = { args: { variant: "secondary", children: "Cancel" } };
export const Ghost: Story = { args: { variant: "ghost", children: "Filter" } };
export const Destructive: Story = {
  args: { variant: "destructive", children: "Write off loan" },
};

export const SizeSmall: Story = { args: { size: "sm", children: "Small" } };
export const SizeMedium: Story = { args: { size: "md", children: "Medium" } };
export const SizeLarge: Story = { args: { size: "lg", children: "Large" } };

export const StateDefault: Story = { args: { children: "Default" } };
export const StateHover: Story = {
  args: { children: "Hover", className: "hover:!bg-[var(--interactive-primary-bg-hover)]" },
};
export const StateDisabled: Story = { args: { disabled: true, children: "Disabled" } };
export const StateLoading: Story = {
  args: {
    disabled: true,
    children: (
      <>
        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent" />
        Saving…
      </>
    ),
  },
};

export const Grid: Story = {
  render: () => (
    <div className="grid grid-cols-4 gap-4">
      {(["primary", "secondary", "ghost", "destructive"] as const).map((variant) => (
        <div key={variant} className="flex flex-col gap-2">
          <Button variant={variant} size="sm">
            {variant} sm
          </Button>
          <Button variant={variant} size="md">
            {variant} md
          </Button>
          <Button variant={variant} size="lg">
            {variant} lg
          </Button>
          <Button variant={variant} disabled>
            {variant} disabled
          </Button>
        </div>
      ))}
    </div>
  ),
};
