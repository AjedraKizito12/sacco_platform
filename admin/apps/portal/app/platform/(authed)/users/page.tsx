import Link from "next/link";
import { Button, Card } from "@sacco/ui";
import type { PlatformUserOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { UsersTable } from "./_components/UsersTable";

export const metadata = { title: "Platform Users" };

export default async function PlatformUsersPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.users.read");

  const { data } = await resources.admin.listUsers();
  const rows = (data ?? []) as PlatformUserOut[];
  const canCreate = userHasPermission(user, "platform.users.write");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Platform Users</h1>
        {canCreate ? (
          <Button asChild>
            <Link href="/platform/users/new">New user</Link>
          </Button>
        ) : null}
      </div>
      <Card className="p-0">
        <UsersTable rows={rows} />
      </Card>
    </div>
  );
}
