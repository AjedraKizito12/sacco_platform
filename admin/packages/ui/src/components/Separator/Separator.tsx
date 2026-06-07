import * as SeparatorPrimitive from "@radix-ui/react-separator";
import * as React from "react";
import { forwardRef, type ComponentPropsWithoutRef } from "react";
import { cn } from "../../utils/cn";

export const Separator = forwardRef<
  React.ElementRef<typeof SeparatorPrimitive.Root>,
  ComponentPropsWithoutRef<typeof SeparatorPrimitive.Root>
>(({ className, orientation = "horizontal", decorative = true, ...props }, ref) => (
  <SeparatorPrimitive.Root
    ref={ref}
    decorative={decorative}
    orientation={orientation}
    className={cn(
      "bg-[var(--border-subtle)]",
      orientation === "horizontal" ? "h-px w-full" : "h-full w-px",
      className,
    )}
    {...props}
  />
));
Separator.displayName = "Separator";
