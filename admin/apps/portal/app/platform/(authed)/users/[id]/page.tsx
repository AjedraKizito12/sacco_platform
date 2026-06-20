import { notFound } from "next/navigation";
import type { PlatformUserOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { AuditBarConnected } from "@/components/AuditBarConnected";
import { UserDetail } from "./_components/UserDetail";

export const metadata = { title: "Platform User" };

export default async function PlatformUserDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.users.read");

  // resources.admin.getUser is typed Promise<never> because admin.ts uses
  // `as never` on its openapi-fetch paths; cast to the real openapi-fetch
  // { data, error } shape until those resource types tighten (out of SP12 scope).
  const { data } = await (
    resources.admin.getUser(id) as Promise<{ data?: PlatformUserOut; error?: unknown }>
  );
  if (!data) notFound();

  return (
    <UserDetail
      user={data}
      canEdit={userHasPermission(user, "platform.users.write")}
      auditBar={<AuditBarConnected entityType="platform_user" entityId={data.id} />}
    />
  );
}
