"use client";

import type { ReactNode } from "react";
import { Button } from "../Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../Dialog";

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange(next: boolean): void;
  title: string;
  description?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  /** Renders the confirm button as `destructive`. */
  destructive?: boolean;
  onConfirm(): void | Promise<void>;
  /** Disable both buttons while a mutation is in flight. */
  busy?: boolean;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  destructive = false,
  onConfirm,
  busy = false,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? (
            <DialogDescription>{description}</DialogDescription>
          ) : null}
        </DialogHeader>
        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? "destructive" : "primary"}
            onClick={() => {
              void onConfirm();
            }}
            disabled={busy}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export interface MakerCheckerConfirmDialogProps
  extends Omit<
    ConfirmDialogProps,
    "title" | "description" | "confirmLabel" | "destructive"
  > {
  /** What the operator is requesting, e.g., "loan disbursement". */
  operationLabel: string;
  /** Subject the operator is acting on, e.g., "loan #L-2026-001234". */
  subjectLabel?: string;
}

/**
 * Locked copy per docs/sacco-design-system-v2.md line 1102 and CLAUDE.md
 * contract K. Do not customise — the maker-checker dialog says exactly
 * this so the dual-state outcome is unambiguous.
 */
export function MakerCheckerConfirmDialog({
  operationLabel,
  subjectLabel,
  ...rest
}: MakerCheckerConfirmDialogProps) {
  const title = subjectLabel
    ? `Request ${operationLabel} on ${subjectLabel}`
    : `Request ${operationLabel}`;
  const description = (
    <span>
      This will create an approval request, not execute the action.
      <br />
      Another authorised user must approve before {operationLabel} runs.
    </span>
  );
  return (
    <ConfirmDialog
      {...rest}
      title={title}
      description={description}
      confirmLabel="Create Approval Request"
    />
  );
}
