import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import type { HTMLAttributes } from "react";
import { cn } from "../../utils/cn";

const badgeVariants = cva(
  [
    "inline-flex h-6 items-center gap-1 rounded-[var(--radius-sm)] px-2",
    "text-[12px] font-medium",
    "[font-feature-settings:'tnum'_1,'lnum'_1]",
  ],
  {
    variants: {
      variant: {
        success: "bg-[var(--status-success-bg)] text-[var(--text-success)]",
        warning: "bg-[var(--status-warning-bg)] text-[var(--text-warning)]",
        danger: "bg-[var(--status-danger-bg)] text-[var(--text-danger)]",
        "danger-solid": "bg-[var(--status-danger-solid-bg)] text-[var(--status-danger-solid-text)]",
        info: "bg-[var(--status-info-bg)] text-[var(--text-info)]",
        neutral: "bg-[var(--status-neutral-bg)] text-[var(--status-neutral-text)]",
        dark: "bg-[var(--status-dark-bg)] text-[var(--status-dark-text)]",
        accent: "bg-[var(--status-accent-bg)] text-[var(--text-accent)]",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {
  withDot?: boolean;
}

export function Badge({
  className,
  variant,
  withDot,
  children,
  ...props
}: BadgeProps): React.JSX.Element {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props}>
      {withDot ? <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden /> : null}
      {children}
    </span>
  );
}

export { badgeVariants };
