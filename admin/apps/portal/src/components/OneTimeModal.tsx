"use client";

import {
  Button,
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@sacco/ui";
import { Copy, Check } from "lucide-react";
import { useState, type ReactNode } from "react";

interface OneTimeModalProps {
  open: boolean;
  onAcknowledge(): void;
  title: string;
  description: string;
  payload: string;
  payloadLabel?: string;
  warningCopy?: ReactNode;
}

/**
 * Single-view "this won't be shown again" modal. Used for:
 *  - Self-service password reset success (token displayed once)
 *  - Admin-initiated tenant-user password reset (sub-plan 32)
 *
 * Forces the user to acknowledge before the modal closes. Provides a
 * one-click copy with a 2s feedback state. Closing fires onAcknowledge —
 * there is no "X" close button and no overlay-click dismissal.
 */
export function OneTimeModal({
  open,
  onAcknowledge,
  title,
  description,
  payload,
  payloadLabel = "Token",
  warningCopy,
}: OneTimeModalProps) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(payload);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
  return (
    <Dialog open={open}>
      <DialogContent
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <DialogBody>
          <p className="mb-4 text-[var(--text-secondary)]">{description}</p>
          {warningCopy && (
            <p className="mb-4 rounded-md bg-[var(--status-warning-bg)] p-3 text-[var(--text-warning)]">
              {warningCopy}
            </p>
          )}
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
              {payloadLabel}
            </p>
            <div className="flex items-center gap-2 rounded-md border border-[var(--border-default)] bg-[var(--surface-sunken)] p-3">
              <code className="flex-1 break-all font-mono text-sm">{payload}</code>
              <Button variant="secondary" size="sm" onClick={copy} type="button">
                {copied ? <Check size={16} /> : <Copy size={16} />}
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
          </div>
        </DialogBody>
        <DialogFooter>
          <Button onClick={onAcknowledge}>
            I&apos;ve recorded this and won&apos;t need it shown again
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
