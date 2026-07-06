"use client";

import type { FormEventHandler, ReactNode } from "react";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../Dialog";
import { cn } from "../../utils/cn";

export interface FormDialogProps {
  /** Whether the dialog is open. Route-driven modals default to true. */
  open?: boolean;
  /**
   * Called when the user dismisses the dialog (close button, Esc, or backdrop).
   * Route-driven modals wire this to `router.back()`; standalone pages push
   * back to the list.
   */
  onDismiss: () => void;
  title: string;
  description?: string;
  onSubmit: FormEventHandler<HTMLFormElement>;
  /** Action buttons rendered in the footer (submit lives here, inside the form). */
  footer: ReactNode;
  /** The field stack. Each child is typically a <FormField> or <FormSection>. */
  children: ReactNode;
  /** Width override; defaults to a comfortable single-form width. */
  className?: string;
}

/**
 * The standard shell for create/edit forms presented as a centered modal over
 * the list behind it. Owns the bounded card chrome (header + dismiss, scrollable
 * body, footer), so consumers only supply fields and actions. The `<form>`
 * wraps body + footer so the footer submit button drives the form.
 */
export function FormDialog({
  open = true,
  onDismiss,
  title,
  description,
  onSubmit,
  footer,
  children,
  className,
}: FormDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onDismiss();
      }}
    >
      <DialogContent
        className={cn("flex max-h-[calc(100vh-4rem)] w-full flex-col gap-0 p-0", className ?? "max-w-2xl")}
      >
        <DialogHeader className="shrink-0 pr-12">
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        <form noValidate onSubmit={onSubmit} className="flex min-h-0 flex-1 flex-col">
          <DialogBody className="flex flex-col gap-6 overflow-y-auto">{children}</DialogBody>
          <DialogFooter className="shrink-0">{footer}</DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
