"use client";

import { Check } from "lucide-react";
import { cn } from "../../utils/cn";

export interface StepperStep {
  id: string;
  label: string;
}

export interface StepperProps {
  steps: StepperStep[];
  currentStepId: string;
  /** Called when a completed step's label is clicked. Upcoming steps are not clickable. */
  onStepClick?(stepId: string): void;
  className?: string;
}

export function Stepper({
  steps,
  currentStepId,
  onStepClick,
  className,
}: StepperProps) {
  const currentIdx = steps.findIndex((s) => s.id === currentStepId);
  return (
    <ol
      aria-label="Progress"
      className={cn("flex w-full items-center gap-2", className)}
    >
      {steps.map((step, idx) => {
        const status =
          idx < currentIdx
            ? "done"
            : idx === currentIdx
              ? "current"
              : "upcoming";
        const clickable = status === "done" && onStepClick !== undefined;
        return (
          <li
            key={step.id}
            className="flex flex-1 items-center gap-2"
            aria-current={status === "current" ? "step" : undefined}
          >
            <button
              type="button"
              disabled={!clickable}
              onClick={clickable ? () => onStepClick(step.id) : undefined}
              className={cn(
                "flex items-center gap-2 rounded-[var(--radius-md)] px-2 py-1 text-[13px]",
                status === "done" &&
                  "text-[var(--text-success)] hover:bg-[var(--surface-hover)]",
                status === "current" &&
                  "font-semibold text-[var(--text-primary)]",
                status === "upcoming" && "text-[var(--text-tertiary)]",
                !clickable && "cursor-default",
              )}
            >
              <span
                className={cn(
                  "grid h-5 w-5 place-content-center rounded-full text-[11px]",
                  status === "done" &&
                    "bg-[var(--status-success-bg)] text-[var(--text-success)]",
                  status === "current" &&
                    "bg-[var(--interactive-primary-bg)] text-[var(--interactive-primary-text)]",
                  status === "upcoming" &&
                    "border border-[var(--border-default)] text-[var(--text-tertiary)]",
                )}
              >
                {status === "done" ? (
                  <Check size={12} strokeWidth={2.25} />
                ) : (
                  idx + 1
                )}
              </span>
              <span>{step.label}</span>
            </button>
            {idx < steps.length - 1 ? (
              <span
                aria-hidden="true"
                className={cn(
                  "h-px flex-1",
                  status === "done"
                    ? "bg-[var(--text-success)]"
                    : "bg-[var(--border-subtle)]",
                )}
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
