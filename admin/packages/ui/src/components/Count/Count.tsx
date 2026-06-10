import type { HTMLAttributes } from "react";
import { cn } from "../../utils/cn";
import { formatCount } from "../../utils/format";

export interface CountProps extends HTMLAttributes<HTMLSpanElement> {
  value: number;
}

export function Count({ value, className, ...props }: CountProps) {
  return (
    <span
      className={cn("[font-feature-settings:'tnum'_1,'lnum'_1]", className)}
      data-value={value}
      {...props}
    >
      {formatCount(value)}
    </span>
  );
}
