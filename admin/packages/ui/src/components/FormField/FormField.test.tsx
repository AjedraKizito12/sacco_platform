import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { FormField } from "./FormField";
import { Input } from "../Input";

interface Values {
  name: string;
}

function Harness({
  defaultValues = { name: "" },
  required = false,
  helpText,
}: {
  defaultValues?: Values;
  required?: boolean;
  helpText?: string;
}) {
  const { control, handleSubmit } = useForm<Values>({
    defaultValues,
    mode: "onBlur",
  });
  return (
    <form onSubmit={handleSubmit(() => {})} noValidate>
      <FormField
        control={control}
        name="name"
        label="Full name"
        required={required}
        {...(helpText !== undefined ? { helpText } : {})}
        render={({ field, id, describedBy, invalid }) => (
          <Input
            id={id}
            aria-invalid={invalid}
            aria-describedby={describedBy}
            {...field}
          />
        )}
      />
      <button type="submit">Submit</button>
    </form>
  );
}

describe("FormField", () => {
  it("renders the label and wires htmlFor → id", () => {
    render(<Harness />);
    const input = screen.getByLabelText("Full name");
    expect(input).toBeInTheDocument();
  });

  it("renders the required asterisk when required", () => {
    render(<Harness required />);
    expect(screen.getByText("*")).toBeInTheDocument();
  });

  it("renders help text linked via aria-describedby", () => {
    render(<Harness helpText="Use your government name." />);
    const input = screen.getByLabelText("Full name");
    const helpId = input.getAttribute("aria-describedby");
    expect(helpId).toBeTruthy();
    expect(document.getElementById(helpId!)?.textContent).toBe(
      "Use your government name.",
    );
  });

  it("surfaces RHF errors with role=alert + aria-describedby points at error", async () => {
    function ErrorHarness() {
      const { control, handleSubmit, setError } = useForm<Values>({
        defaultValues: { name: "" },
      });
      return (
        <form
          onSubmit={handleSubmit(() => {
            setError("name", { type: "manual", message: "Name is required" });
          })}
        >
          <FormField
            control={control}
            name="name"
            label="Full name"
            render={({ field, id, describedBy, invalid }) => (
              <Input
                id={id}
                aria-invalid={invalid}
                aria-describedby={describedBy}
                {...field}
              />
            )}
          />
          <button type="submit">Submit</button>
        </form>
      );
    }
    render(<ErrorHarness />);
    await userEvent.click(screen.getByText("Submit"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Name is required");
    expect(screen.getByLabelText("Full name")).toHaveAttribute(
      "aria-describedby",
      alert.id,
    );
  });
});
