import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "../../utils/cn";

const buttonVariants = cva(
  // Base styles: 40px height, 12px radius, focus-visible ring per tokens
  [
    "inline-flex items-center justify-center gap-2",
    "rounded-[var(--radius-md)] font-medium",
    "transition-colors duration-150",
    "focus-visible:outline-2 focus-visible:outline-offset-2",
    "focus-visible:outline-[var(--border-focus)]",
    "disabled:cursor-not-allowed disabled:opacity-100",
    // Tabular numerals so any numeric label aligns in toolbars
    "[font-feature-settings:'tnum'_1,'lnum'_1]",
  ],
  {
    variants: {
      variant: {
        primary: [
          "bg-[var(--interactive-primary-bg)]",
          "text-[var(--interactive-primary-text)]",
          "hover:bg-[var(--interactive-primary-bg-hover)]",
          "active:bg-[var(--interactive-primary-bg-active)]",
          "disabled:bg-[var(--interactive-primary-bg-disabled)]",
        ],
        secondary: [
          "bg-[var(--interactive-secondary-bg)]",
          "text-[var(--interactive-secondary-text)]",
          "border border-[var(--interactive-secondary-border)]",
          "hover:bg-[var(--interactive-secondary-bg-hover)]",
          "active:bg-[var(--interactive-secondary-bg-active)]",
        ],
        ghost: [
          "bg-transparent",
          "text-[var(--interactive-ghost-text)]",
          "hover:bg-[var(--interactive-ghost-bg-hover)]",
          "hover:text-[var(--interactive-ghost-text-hover)]",
          "active:bg-[var(--interactive-ghost-bg-active)]",
        ],
        destructive: [
          "bg-[var(--interactive-destructive-bg)]",
          "text-[var(--interactive-destructive-text)]",
          "hover:bg-[var(--interactive-destructive-bg-hover)]",
        ],
      },
      size: {
        sm: "h-[var(--height-control-sm)] px-3 text-[13px]",
        md: "h-[var(--height-control)] px-4 text-[var(--text-body)]",
        lg: "h-[var(--height-control-lg)] px-5 text-[15px]",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  /**
   * When true, renders as a Radix Slot — clones the single child and
   * applies the button classes to it. Useful for wrapping <Link>.
   */
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
