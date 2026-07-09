// admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/page.tsx
import type { KycSubmissionListItemOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { KycSubmissionsTable } from "./_components/KycSubmissionsTable";

export const metadata = { title: "KYC submissions" };

export default async function KycSubmissionsPage() {
  const { resources } = await getTenantPageContext();
  const { data, error } = await (resources.members.listKycSubmissions() as Promise<{
    data?: KycSubmissionListItemOut[];
    error?: unknown;
  }>);
  if (!data) {
    throw new Error(`Failed to load KYC submissions: ${JSON.stringify(error)}`);
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">KYC submissions</h1>
      <KycSubmissionsTable rows={data} />
    </div>
  );
}
