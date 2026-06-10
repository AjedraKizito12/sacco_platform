import type { Meta, StoryObj } from "@storybook/react";
import { useForm } from "react-hook-form";
import { FormField } from "./FormField";
import { Input } from "../Input";

const meta: Meta<typeof FormField> = {
  title: "Forms/FormField",
  component: FormField,
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj;

function Demo({
  required,
  helpText,
}: {
  required?: boolean;
  helpText?: string;
}) {
  const { control } = useForm<{ name: string }>({
    defaultValues: { name: "" },
  });
  return (
    <div style={{ maxWidth: 360 }}>
      <FormField
        control={control}
        name="name"
        label="Member full name"
        {...(required !== undefined ? { required } : {})}
        {...(helpText !== undefined ? { helpText } : {})}
        render={({ field, id, describedBy, invalid }) => (
          <Input
            id={id}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            placeholder="Mary Akello"
            {...field}
          />
        )}
      />
    </div>
  );
}

export const Default: Story = { render: () => <Demo /> };
export const Required: Story = { render: () => <Demo required /> };
export const WithHelp: Story = {
  render: () => <Demo helpText="As it appears on national ID." />,
};
