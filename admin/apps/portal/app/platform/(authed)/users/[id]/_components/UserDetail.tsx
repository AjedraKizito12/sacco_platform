import type { ReactNode } from "react";
import Link from "next/link";
import {
  Button,
  Card,
  FormattedDateTime,
  ReadOnlyField,
  RelativeTime,
  StatusBadge,
} from "@sacco/ui";
import { PLATFORM_ROLE_LABELS, type PlatformUserOut } from "@sacco/schemas";

export function UserDetail({
  user,
  canEdit,
  auditBar,
}: {
  user: PlatformUserOut;
  canEdit: boolean;
  auditBar: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-[var(--text-h3)] font-semibold">{user.full_name}</h1>
          <StatusBadge entity="platform_user" status={user.is_active ? "active" : "inactive"} />
        </div>
        {canEdit ? (
          <Button asChild variant="secondary">
            <Link href={`/platform/users/${user.id}/edit`}>Edit</Link>
          </Button>
        ) : null}
      </div>

      <Card className="grid grid-cols-2 gap-5 p-6">
        <ReadOnlyField label="Email" value={user.email} />
        <ReadOnlyField label="Role" value={PLATFORM_ROLE_LABELS[user.role]} />
        <ReadOnlyField
          label="Last login"
          value={user.last_login_at ? <RelativeTime value={user.last_login_at} /> : "Never"}
        />
        <ReadOnlyField label="Created" value={<FormattedDateTime value={user.created_at} />} />
      </Card>

      {auditBar}
    </div>
  );
}
