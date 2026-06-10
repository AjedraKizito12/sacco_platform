import { TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../utils/cn";

export interface MakerCheckerBannerProps {
  /** Approval request id used in the link. */
  approvalRequestId: string;
  /** Operation label, e.g., "Loan disbursement". */
  operationLabel: string;
  requesterName: string;
  /** ISO timestamp; consumers can pass a React node (e.g., `<FormattedDateTime>`). */
  requestedAt: string | ReactNode;
  quorumRequired: number;
  quorumCurrent: number;
  /** Action node (the consumer wires the link). */
  action: ReactNode;
  className?: string;
}

export function MakerCheckerBanner({
  operationLabel,
  requesterName,
  requestedAt,
  quorumRequired,
  quorumCurrent,
  action,
  className,
}: MakerCheckerBannerProps) {
  const remaining = Math.max(0, quorumRequired - quorumCurrent);
  return (
    <div
      role="status"
      className={cn(
        "flex items-start gap-3 rounded-[var(--radius-md)] border px-4 py-3",
        "border-[var(--text-warning)] bg-[var(--status-warning-bg)] text-[var(--text-warning)]",
        className,
      )}
    >
      <TriangleAlert size={20} strokeWidth={1.75} aria-hidden />
      <div className="flex-1 text-[13px] text-[var(--text-primary)]">
        <p className="font-semibold">Pending Approval</p>
        <p className="mt-1">
          {operationLabel} requested by{" "}
          <strong>{requesterName}</strong> on {requestedAt}.
        </p>
        <p>
          Requires {remaining} more {remaining === 1 ? "approval" : "approvals"} (
          {quorumCurrent} of {quorumRequired} so far).
        </p>
      </div>
      <div className="ml-auto">{action}</div>
    </div>
  );
}
