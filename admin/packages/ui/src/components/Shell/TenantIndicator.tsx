import { Building2 } from "lucide-react";
import { Badge } from "../Badge";
import { cn } from "../../utils/cn";

export interface TenantIndicatorProps {
  tenantName: string;
  impersonating?: boolean;
  className?: string;
}

export function TenantIndicator({
  tenantName,
  impersonating,
  className,
}: TenantIndicatorProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-[var(--radius-md)]",
        "border border-[var(--border-subtle)] bg-[var(--surface-sunken)]",
        "h-[var(--height-control-sm)] px-3 text-[13px] text-[var(--text-secondary)]",
        className,
      )}
    >
      <Building2 size={14} strokeWidth={1.75} aria-hidden />
      <span className="font-medium text-[var(--text-primary)]">{tenantName}</span>
      {impersonating ? (
        <Badge variant="warning" withDot>
          Impersonating
        </Badge>
      ) : null}
    </div>
  );
}
