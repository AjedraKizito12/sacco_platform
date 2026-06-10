import { Inbox } from "lucide-react";
import type { ReactNode } from "react";

export interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <Inbox
        size={48}
        strokeWidth={1.75}
        className="text-[var(--icon-default)]"
        aria-hidden
      />
      <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">
        {title}
      </h3>
      {description ? (
        <p className="max-w-md text-[var(--text-secondary)]">{description}</p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
