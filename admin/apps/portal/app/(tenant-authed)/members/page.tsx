// admin/apps/portal/app/(tenant-authed)/members/page.tsx
import Link from "next/link";
import { Button } from "@sacco/ui";
import type { MemberOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { MembersTable } from "./_components/MembersTable";

export const metadata = { title: "Members" };

export default async function MembersPage() {
  const { resources } = await getTenantPageContext();
  const { data } = await (resources.members.list({}) as Promise<{
    data?: MemberOut[];
    error?: unknown;
  }>);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Members</h1>
        <Button asChild>
          <Link href="/members/new">Register member</Link>
        </Button>
      </div>
      <MembersTable rows={data ?? []} />
    </div>
  );
}
