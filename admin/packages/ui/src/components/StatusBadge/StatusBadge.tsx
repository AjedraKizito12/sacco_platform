import { Badge } from "../Badge";
import { type StatusEntity, resolveStatus } from "./status-maps";

export interface StatusBadgeProps {
  entity: StatusEntity;
  status: string;
  /** Override the looked-up label (e.g., for localisation). */
  label?: string;
  withDot?: boolean;
  className?: string;
}

export function StatusBadge({
  entity,
  status,
  label,
  withDot,
  className,
}: StatusBadgeProps) {
  const entry = resolveStatus(entity, status);
  if (!entry) {
    // Unknown status — render the raw value in a neutral badge so the
    // operator can see what came through. Never crash.
    return (
      <Badge variant="neutral" withDot={withDot} className={className}>
        {label ?? status}
      </Badge>
    );
  }
  return (
    <Badge variant={entry.variant} withDot={withDot} className={className}>
      {label ?? entry.label}
    </Badge>
  );
}
