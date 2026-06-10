import { Lock } from "lucide-react";

export function PermissionDeniedState() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <Lock
        size={48}
        strokeWidth={1.75}
        className="text-[var(--icon-default)]"
        aria-hidden
      />
      <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">
        You don&apos;t have permission to view this list
      </h3>
      <p className="max-w-md text-[var(--text-secondary)]">
        Contact your administrator if you believe this is wrong.
      </p>
    </div>
  );
}
