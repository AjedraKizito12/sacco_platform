import * as React from "react";
import { forwardRef, type HTMLAttributes, type ReactNode } from "react";
import { cn } from "../../utils/cn";

export const Card = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "rounded-[var(--radius-card)] border bg-[var(--surface-elevated)] p-6",
        "border-[var(--border-subtle)] shadow-[var(--shadow-sm)]",
        className,
      )}
      {...props}
    />
  ),
);
Card.displayName = "Card";

export const CardHeader = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("border-b border-[var(--border-subtle)] px-6 py-5", className)}
      {...props}
    />
  ),
);
CardHeader.displayName = "CardHeader";

export const CardBody = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} className={cn("p-6", className)} {...props} />,
);
CardBody.displayName = "CardBody";

export const CardFooter = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("border-t border-[var(--border-subtle)] px-6 py-4", className)}
      {...props}
    />
  ),
);
CardFooter.displayName = "CardFooter";

export interface KpiCardProps {
  label: string;
  value: ReactNode;
  trend?: { direction: "up" | "down" | "flat"; label: string };
  className?: string;
}

export function KpiCard({ label, value, trend, className }: KpiCardProps): React.JSX.Element {
  return (
    <Card className={cn("flex flex-col gap-2 p-6", className)}>
      <p className="text-[13px] font-medium text-[var(--text-tertiary)]">{label}</p>
      <p className="text-[28px] font-semibold text-[var(--text-primary)] [font-feature-settings:'tnum'_1,'lnum'_1]">
        {value}
      </p>
      {trend ? (
        <p
          className={cn(
            "text-[12px]",
            trend.direction === "up" && "text-[var(--text-success)]",
            trend.direction === "down" && "text-[var(--text-danger)]",
            trend.direction === "flat" && "text-[var(--text-tertiary)]",
          )}
        >
          {trend.label}
        </p>
      ) : null}
    </Card>
  );
}
