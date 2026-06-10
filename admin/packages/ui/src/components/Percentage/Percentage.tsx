import type { HTMLAttributes } from "react";
import { cn } from "../../utils/cn";
import { formatPercentage } from "../../utils/format";

export interface PercentageProps extends HTMLAttributes<HTMLSpanElement> {
  /** Decimal-as-string value (0-100). */
  value: string;
}

export function Percentage({ value, className, ...props }: PercentageProps) {
  return (
    <span
      className={cn("[font-feature-settings:'tnum'_1,'lnum'_1]", className)}
      data-value={value}
      {...props}
    >
      {formatPercentage(value)}
    </span>
  );
}
