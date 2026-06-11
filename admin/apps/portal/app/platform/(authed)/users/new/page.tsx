import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { CreateUserForm } from "./_components/CreateUserForm";

export const metadata = { title: "New Platform User" };

export default async function NewPlatformUserPage() {
  const { user } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.users.write");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">New platform user</h1>
      <CreateUserForm />
    </div>
  );
}
