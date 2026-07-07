import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { CreateUserForm } from "./_components/CreateUserForm";

export const metadata = { title: "New Platform User" };

export default async function NewPlatformUserPage() {
  const { user } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.users.write");

  return <CreateUserForm />;
}
