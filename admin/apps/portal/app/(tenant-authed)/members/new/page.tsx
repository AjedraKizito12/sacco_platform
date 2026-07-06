// admin/apps/portal/app/(tenant-authed)/members/new/page.tsx
import { getTenantPageContext } from "@/auth/server-page-context";
import { CreateMemberForm } from "./_components/CreateMemberForm";

export const metadata = { title: "Register member" };

export default async function NewMemberPage() {
  await getTenantPageContext();
  return <CreateMemberForm />;
}
