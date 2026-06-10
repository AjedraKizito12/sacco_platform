import { AlertOctagon } from "lucide-react";
import { Button } from "../../Button";

export interface ErrorStateProps {
  message: string;
  requestId?: string | null;
  onRetry?(): void;
}

export function ErrorState({ message, requestId, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <AlertOctagon
        size={48}
        strokeWidth={1.75}
        className="text-[var(--text-danger)]"
        aria-hidden
      />
      <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">
        Something went wrong
      </h3>
      <p className="max-w-md text-[var(--text-secondary)]">{message}</p>
      {requestId ? (
        <p className="text-[12px] text-[var(--text-tertiary)]">
          Request ID: <code>{requestId}</code>
        </p>
      ) : null}
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}
