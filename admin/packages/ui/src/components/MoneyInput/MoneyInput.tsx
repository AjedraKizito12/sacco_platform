"use client";

import {
  forwardRef,
  useCallback,
  useState,
  type ChangeEvent,
  type FocusEvent,
  type InputHTMLAttributes,
} from "react";
import { cn } from "../../utils/cn";
import { fieldNumericInputClass, fieldShellClass } from "../../utils/field-shell";
import { useTenantCurrency } from "../../context/TenantCurrency";
import { canonicalise, formatTyping, stripFormatting } from "./format-helpers";

export interface MoneyInputProps
  extends Omit<
    InputHTMLAttributes<HTMLInputElement>,
    "value" | "onChange" | "type"
  > {
  /** Decimal-as-string. Empty string means no value. */
  value: string;
  onValueChange(next: string): void;
  /** Override the provider's currency. */
  currency?: string;
  /** Permit a leading minus sign. Default false. */
  allowNegative?: boolean;
}

export const MoneyInput = forwardRef<HTMLInputElement, MoneyInputProps>(
  function MoneyInput(
    {
      value,
      onValueChange,
      currency,
      allowNegative = false,
      onBlur,
      className,
      ...rest
    },
    ref,
  ) {
    const provider = useTenantCurrency();
    const effectiveCurrency = currency ?? provider.currency;

    // The visible string includes thousands separators; the value prop is
    // the canonical Decimal-as-string. We re-derive the visible string
    // whenever value changes externally.
    const [display, setDisplay] = useState(() => formatTyping(value));
    if (formatTyping(stripFormatting(display)) !== formatTyping(value)) {
      setDisplay(formatTyping(value));
    }

    const onChange = useCallback(
      (e: ChangeEvent<HTMLInputElement>) => {
        let stripped = stripFormatting(e.target.value);
        if (!allowNegative && stripped.startsWith("-")) {
          stripped = stripped.slice(1);
        }
        setDisplay(formatTyping(stripped));
        onValueChange(stripped);
      },
      [allowNegative, onValueChange],
    );

    const handleBlur = useCallback(
      (e: FocusEvent<HTMLInputElement>) => {
        const stripped = stripFormatting(display);
        const canonical = canonicalise(stripped, effectiveCurrency);
        setDisplay(formatTyping(canonical));
        onValueChange(canonical);
        onBlur?.(e);
      },
      [display, effectiveCurrency, onBlur, onValueChange],
    );

    return (
      <div className={cn(fieldShellClass, className)}>
        <span
          aria-hidden="true"
          className="select-none rounded-[var(--radius-sm)] bg-[var(--surface-sunken)] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]"
        >
          {effectiveCurrency}
        </span>
        <input
          ref={ref}
          inputMode="decimal"
          autoComplete="off"
          className={fieldNumericInputClass}
          value={display}
          onChange={onChange}
          onBlur={handleBlur}
          {...rest}
        />
      </div>
    );
  },
);
