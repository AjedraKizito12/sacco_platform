import { notFound } from "next/navigation";
import type { PlatformUserOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { EditUserForm } from "./_components/EditUserForm";

export const metadata = { title: "Edit Platform User" };

export default async function EditPlatformUserPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.users.write");

  // resources.admin.getUser is typed Promise<never> because admin.ts uses
  // `as never` on its openapi-fetch paths; cast to the real openapi-fetch
  // { data, error } shape until those resource types tighten (out of SP12 scope).
  const { data } = await (
    resources.admin.getUser(id) as Promise<{ data?: PlatformUserOut; error?: unknown }>
  );
  if (!data) notFound();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Edit platform user</h1>
      <EditUserForm user={data} />
    </div>
  );
}
