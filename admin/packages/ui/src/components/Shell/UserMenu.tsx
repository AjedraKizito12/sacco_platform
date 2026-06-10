import { LogOut, User } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../DropdownMenu";
import { cn } from "../../utils/cn";

export interface UserMenuProps {
  fullName: string;
  email: string;
  /** Optional role/permission badge text shown under the email. */
  contextLabel?: string;
  onProfile?(): void;
  onSignOut(): void;
  className?: string;
}

function initials(fullName: string): string {
  return fullName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

export function UserMenu({
  fullName,
  email,
  contextLabel,
  onProfile,
  onSignOut,
  className,
}: UserMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`User menu for ${fullName}`}
          className={cn(
            "inline-flex h-[var(--height-control-sm)] w-[var(--height-control-sm)] items-center justify-center rounded-full",
            "bg-[var(--surface-sunken)] text-[13px] font-medium text-[var(--text-primary)]",
            "hover:bg-[var(--surface-active)]",
            "focus-visible:outline-2 focus-visible:outline-[var(--border-focus)]",
            className,
          )}
        >
          {initials(fullName)}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[220px]">
        <DropdownMenuLabel>
          <div className="text-[13px] font-medium text-[var(--text-primary)]">
            {fullName}
          </div>
          <div className="text-[12px] text-[var(--text-tertiary)]">{email}</div>
          {contextLabel ? (
            <div className="mt-1 text-[11px] font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
              {contextLabel}
            </div>
          ) : null}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {onProfile ? (
          <DropdownMenuItem onSelect={onProfile}>
            <User size={14} strokeWidth={1.75} className="mr-2" />
            Profile
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuItem onSelect={onSignOut}>
          <LogOut size={14} strokeWidth={1.75} className="mr-2" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
