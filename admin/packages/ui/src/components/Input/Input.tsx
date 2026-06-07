import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "../../utils/cn";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  error?: boolean;
  success?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, error, success, type = "text", ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "h-[var(--height-control)] w-full px-3",
        "rounded-[var(--radius-md)] border bg-[var(--surface-elevated)]",
        "text-[var(--text-body)] text-[var(--text-primary)]",
        "placeholder:text-[var(--text-disabled)]",
        "border-[var(--border-default)]",
        "transition-colors duration-150",
        "hover:border-[var(--border-strong)]",
        "focus-visible:border-[var(--border-focus)] focus-visible:outline-none",
        "focus-visible:shadow-[var(--shadow-focus)]",
        "disabled:cursor-not-allowed disabled:bg-[var(--surface-disabled)]",
        "disabled:text-[var(--text-disabled)]",
        "read-only:bg-[var(--surface-readonly)]",
        "read-only:border-[var(--border-subtle)]",
        error && [
          "border-[var(--border-danger)]",
          "focus-visible:shadow-[var(--shadow-focus-danger)]",
        ],
        success && "border-[var(--border-success)]",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
