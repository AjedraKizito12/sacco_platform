"use client";

import {
  forwardRef,
  useCallback,
  type ChangeEvent,
  type FocusEvent,
  type InputHTMLAttributes,
} from "react";
import { cn } from "../../utils/cn";

export interface PercentageInputProps
  extends Omit<
    InputHTMLAttributes<HTMLInputElement>,
    "value" | "onChange" | "type"
  > {
  /** Decimal-as-string. Empty string means no value. */
  value: string;
  onValueChange(next: string): void;
  /** Clamp to [min, max] on blur. Defaults to [0, 100]. */
  min?: number;
  max?: number;
}

/** Strip everything except digits + a single decimal point. */
function strip(input: string): string {
  const digits = input.replace(/[^0-9.]/g, "");
  const firstDot = digits.indexOf(".");
  if (firstDot === -1) return digits;
  return `${digits.slice(0, firstDot)}.${digits
    .slice(firstDot + 1)
    .replace(/\./g, "")}`;
}

/** Truncate the fractional part to 2 digits. */
function clampDecimals(s: string): string {
  const [a, b] = s.split(".");
  if (b === undefined) return a ?? "";
  return `${a}.${b.slice(0, 2)}`;
}

export const PercentageInput = forwardRef<
  HTMLInputElement,
  PercentageInputProps
>(function PercentageInput(
  { value, onValueChange, min = 0, max = 100, onBlur, className, ...rest },
  ref,
) {
  const onChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const next = clampDecimals(strip(e.target.value));
      onValueChange(next);
    },
    [onValueChange],
  );

  const handleBlur = useCallback(
    (e: FocusEvent<HTMLInputElement>) => {
      if (value === "") {
        onBlur?.(e);
        return;
      }
      const numeric = Number.parseFloat(value);
      if (!Number.isFinite(numeric)) {
        onValueChange("");
        onBlur?.(e);
        return;
      }
      const clamped = Math.min(max, Math.max(min, numeric));
      onValueChange(clamped.toFixed(2));
      onBlur?.(e);
    },
    [max, min, onBlur, onValueChange, value],
  );

  return (
    <div
      className={cn(
        "flex h-[var(--height-control-md)] items-center gap-2 rounded-[var(--radius-md)]",
        "border border-[var(--border-default)] bg-[var(--surface-elevated)]",
        "focus-within:border-[var(--border-focus)] focus-within:shadow-[var(--shadow-focus)]",
        "px-3",
        className,
      )}
    >
      <input
        ref={ref}
        inputMode="decimal"
        autoComplete="off"
        className={cn(
          "h-full flex-1 bg-transparent text-right text-[14px] outline-none",
          "[font-feature-settings:'tnum'_1,'lnum'_1]",
          "[appearance:textfield] [-webkit-appearance:textfield]",
          "[&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none",
        )}
        value={value}
        onChange={onChange}
        onBlur={handleBlur}
        {...rest}
      />
      <span
        aria-hidden="true"
        className="select-none text-[13px] text-[var(--text-tertiary)]"
      >
        %
      </span>
    </div>
  );
});
