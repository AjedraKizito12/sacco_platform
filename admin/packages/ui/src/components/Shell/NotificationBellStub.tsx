import { Bell } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../Tooltip";

export function NotificationBellStub() {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            disabled
            aria-label="Notifications (coming soon)"
            className="inline-flex h-[var(--height-control-sm)] w-[var(--height-control-sm)] items-center justify-center rounded-[var(--radius-md)] text-[var(--icon-default)] hover:bg-[var(--surface-hover)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Bell size={18} strokeWidth={1.75} aria-hidden />
          </button>
        </TooltipTrigger>
        <TooltipContent>Notifications coming soon</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
