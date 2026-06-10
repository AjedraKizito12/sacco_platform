"use client";

import { type ReactElement, useId } from "react";
import {
  Controller,
  type Control,
  type ControllerRenderProps,
  type FieldPath,
  type FieldValues,
} from "react-hook-form";
import { cn } from "../../utils/cn";
import { Label } from "../Label";

export interface FormFieldProps<
  TFieldValues extends FieldValues,
  TName extends FieldPath<TFieldValues>,
> {
  control: Control<TFieldValues>;
  name: TName;
  label: string;
  /** Marks the field as required + appends the asterisk per spec line 542-546. */
  required?: boolean;
  helpText?: string;
  /** Renders the inner field. Receives the RHF field handlers + a stable id. */
  render(args: {
    field: ControllerRenderProps<TFieldValues, TName>;
    id: string;
    describedBy: string | undefined;
    invalid: boolean;
  }): ReactElement;
  className?: string;
}

export function FormField<
  TFieldValues extends FieldValues,
  TName extends FieldPath<TFieldValues>,
>({
  control,
  name,
  label,
  required = false,
  helpText,
  render,
  className,
}: FormFieldProps<TFieldValues, TName>) {
  const generatedId = useId();
  const id = `field-${generatedId}`;
  const helpId = helpText ? `${id}-help` : undefined;
  const errorId = `${id}-error`;
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => {
        const invalid = Boolean(fieldState.error);
        const describedBy = invalid ? errorId : helpId;
        return (
          <div className={cn("flex flex-col gap-1.5", className)}>
            <Label htmlFor={id}>
              {label}
              {required ? (
                <span
                  aria-hidden="true"
                  className="ml-0.5 text-[var(--text-danger)]"
                >
                  *
                </span>
              ) : null}
            </Label>
            {render({ field, id, describedBy, invalid })}
            {invalid ? (
              <p
                id={errorId}
                role="alert"
                className="text-[12px] text-[var(--text-danger)]"
              >
                {fieldState.error?.message ?? "Invalid value"}
              </p>
            ) : helpText ? (
              <p
                id={helpId}
                className="text-[12px] text-[var(--text-tertiary)]"
              >
                {helpText}
              </p>
            ) : null}
          </div>
        );
      }}
    />
  );
}
