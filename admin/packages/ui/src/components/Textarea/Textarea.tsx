import { forwardRef, type TextareaHTMLAttributes } from "react";
import { cn } from "../../utils/cn";

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, error, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "min-h-[96px] w-full resize-y p-3",
        "rounded-[var(--radius-md)] border bg-[var(--surface-elevated)]",
        "text-[var(--text-body)] text-[var(--text-primary)]",
        "border-[var(--border-default)]",
        "focus-visible:border-[var(--border-focus)] focus-visible:outline-none",
        "focus-visible:shadow-[var(--shadow-focus)]",
        "disabled:cursor-not-allowed disabled:bg-[var(--surface-disabled)]",
        error && "border-[var(--border-danger)]",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";
